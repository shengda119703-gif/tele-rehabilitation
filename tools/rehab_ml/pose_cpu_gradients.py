"""Explicit CPU offline-training convolution weight accumulation policy.

Keep model/gradient/state dtype float32. Use float64 intermediates for SiLU,
convolution weight accumulation and explicit CPU AdamW updates, then cast
back to the parameter dtype. This is not checkpoint/state truncation.
No inference/global module patch, and no promise about other environments.
"""
from contextlib import contextmanager
import math
import torch

VERSION = 'fp64_conv_weight_accumulation_v1'
OPTIMIZER_VERSION = 'cpu_adamw_fp64_intermediates_fp32_state_v2'
ACTIVATION_VERSION = 'cpu_silu_fp64_intermediate_v1'


class CPUAdamW(torch.optim.AdamW):
    """AdamW equations with explicit float64 intermediates on CPU.

    Keep moments, step and parameter groups compatible with state_dict recovery.
    Keep stored moments/parameters float32; calculate each moment and parameter
    update in float64 before its single dtype cast. This is a named policy, not
    bitwise equivalence to the default Torch AdamW or an accuracy claim.
    """
    def __init__(self, parameters, *, lr, weight_decay):
        super().__init__(parameters, lr=lr, weight_decay=weight_decay, foreach=False, fused=False)

    @torch.no_grad()
    def step(self, closure=None):
        if closure is not None:
            raise ValueError('bounded_cpu_adamw_does_not_accept_closures')
        # Validate the entire update before mutating any parameter/state.
        for group in self.param_groups:
            if any(group.get(flag, False) for flag in ('amsgrad', 'maximize', 'capturable', 'differentiable', 'foreach', 'fused')):
                raise ValueError('bounded_cpu_adamw_explicit_policy_required')
            for parameter in group['params']:
                gradient = parameter.grad
                if gradient is not None and (parameter.device.type != 'cpu' or parameter.dtype != torch.float32
                        or gradient.is_sparse or gradient.dtype != torch.float32
                        or not torch.isfinite(gradient).all()):
                    raise ValueError('bounded_cpu_adamw_finite_dense_float32_required')
        for group in self.param_groups:
            beta1, beta2 = group['betas']
            for parameter in group['params']:
                gradient = parameter.grad
                if gradient is None:
                    continue
                state = self.state[parameter]
                if not state:
                    state.update(step=torch.zeros((), dtype=torch.float32),
                        exp_avg=torch.zeros_like(parameter, memory_format=torch.preserve_format),
                        exp_avg_sq=torch.zeros_like(parameter, memory_format=torch.preserve_format))
                state['step'].add_(1)
                moment, square = state['exp_avg'], state['exp_avg_sq']
                wide_gradient = gradient.double()
                moment.copy_(moment.double()*beta1 + wide_gradient*(1-beta1))
                square.copy_(square.double()*beta2 + wide_gradient.square()*(1-beta2))
                step = int(state['step'].item())
                denominator = square.double().sqrt()/math.sqrt(1-beta2**step) + group['eps']
                delta = (moment.double()/denominator)*(group['lr']/(1-beta1**step))
                parameter.copy_(parameter.double()*(1-group['lr']*group['weight_decay']) - delta)


def weight_gradient(inputs, grad_output, weight_shape, stride, padding, dilation, groups):
    import torch
    import torch.nn.functional as functional
    if (inputs.device.type != 'cpu' or grad_output.device.type != 'cpu'
            or inputs.dtype != torch.float32 or grad_output.dtype != torch.float32
            or inputs.ndim != 4 or grad_output.ndim != 4 or len(weight_shape) != 4
            or inputs.shape[0] != grad_output.shape[0] or inputs.shape[0] < 1
            or groups < 1 or weight_shape[0] % groups
            or inputs.shape[1] != weight_shape[1]*groups
            or grad_output.shape[1] != weight_shape[0]):
        raise ValueError('explicit_cpu_float32_conv_gradient_shapes_required')
    outputs_per_group = weight_shape[0]//groups
    width = weight_shape[1]*weight_shape[2]*weight_shape[3]
    accumulator = torch.zeros((groups, outputs_per_group, width), dtype=torch.float64)
    # One sample's unfolded matrix at a time, never batch_size copies in fp64.
    for sample in range(inputs.shape[0]):
        columns = functional.unfold(inputs[sample:sample+1].double(), weight_shape[2:],
                                    dilation=dilation, padding=padding, stride=stride)
        length = columns.shape[-1]
        if grad_output.shape[2]*grad_output.shape[3] != length:
            raise ValueError('conv_gradient_spatial_shape_mismatch')
        columns = columns.reshape(groups, width, length)
        outgoing = grad_output[sample].double().reshape(groups, outputs_per_group, length)
        accumulator.add_(torch.bmm(outgoing, columns.transpose(1, 2)))
    return accumulator.reshape(weight_shape).to(dtype=inputs.dtype)


@contextmanager
def cpu_conv_gradients(model):
    """Owned model's training-only hooks, always removed before validation.

The locked YOLO architecture uses each trainable conv once per backward.
Reject unsupported shared/reentrant calls rather than reuse a stale input.
"""
    import torch
    handles, contexts = [], []
    try:
        for module in model.modules():
            if isinstance(module, torch.nn.SiLU):
                def activation_input(layer, arguments):
                    if not model.training:
                        return
                    value = arguments[0]
                    if value.device.type != 'cpu' or value.dtype != torch.float32:
                        raise ValueError('cpu_silu_policy_requires_float32_input')
                    return (value.double(),)
                def activation_output(layer, arguments, result):
                    return result.float() if model.training else None
                handles.extend((module.register_forward_pre_hook(activation_input),
                                module.register_forward_hook(activation_output)))
                continue
            if not isinstance(module, torch.nn.Conv2d) or not module.weight.requires_grad:
                continue
            if (module.weight.device.type != 'cpu' or module.weight.dtype != torch.float32
                    or module.padding_mode != 'zeros'):
                raise ValueError('cpu_conv_gradient_policy_requires_float32_zero_padding')
            context = {}
            contexts.append(context)
            def forward(layer, arguments, output, context=context):
                if not layer.training or not torch.is_grad_enabled():
                    return
                if context or len(arguments) != 1 or not output.requires_grad:
                    raise RuntimeError('cpu_conv_shared_or_invalid_training_forward')
                context['input'] = arguments[0].detach()
                def capture(gradient):
                    context['output_gradient'] = gradient.detach()
                handles.append(output.register_hook(capture))
            def gradient(native, module=module, context=context):
                if set(context) != {'input', 'output_gradient'}:
                    raise RuntimeError('cpu_conv_gradient_requires_current_forward_and_backward')
                inputs, outgoing = context.pop('input'), context.pop('output_gradient')
                return weight_gradient(inputs, outgoing, module.weight.shape, module.stride,
                                       module.padding, module.dilation, module.groups)
            handles.extend((module.register_forward_hook(forward), module.weight.register_hook(gradient)))
        yield
    finally:
        for handle in handles:
            handle.remove()
        for context in contexts:
            context.clear()
