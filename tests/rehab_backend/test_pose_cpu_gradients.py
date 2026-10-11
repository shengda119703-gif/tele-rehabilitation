"""TEST analytic gradients and hook lifecycle, not human accuracy evidence."""
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.rehab_ml.pose_cpu_gradients import CPUAdamW, cpu_conv_gradients, weight_gradient


class CPUGradientTests(unittest.TestCase):
    def test_activation_uses_double_intermediates_and_restores_owned_hooks(self):
        import torch
        model = torch.nn.Sequential(torch.nn.SiLU(inplace=True))
        inputs = torch.linspace(-9, 9, 97, requires_grad=True)
        reference_input = inputs.detach().double().requires_grad_(True)
        expected = torch.nn.functional.silu(reference_input).float()
        expected.sum().backward()
        with cpu_conv_gradients(model):
            actual = model(inputs)
            actual.sum().backward()
        self.assertEqual(actual.dtype, torch.float32)
        self.assertTrue(torch.equal(actual, expected))
        self.assertTrue(torch.equal(inputs.grad, reference_input.grad.float()))
        self.assertFalse(model[0]._forward_pre_hooks)
        self.assertFalse(model[0]._forward_hooks)

    def test_optimizer_matches_adamw_equations_not_native_rounding_contract(self):
        import torch
        parameter = torch.nn.Parameter(torch.tensor([.25, -.75, 1.]))
        expected = parameter.detach().double().clone()
        first, second = torch.zeros(3, dtype=torch.float64), torch.zeros(3, dtype=torch.float64)
        optimizer = CPUAdamW([parameter], lr=.001, weight_decay=.01)
        for step in range(1, 5):
            gradient = torch.tensor([.2*step, -.3, .4/step])
            parameter.grad = gradient.clone()
            first = .9*first + .1*gradient.double()
            second = .999*second + .001*gradient.double().square()
            expected *= 1-.001*.01
            expected -= .001*(first/(1-.9**step))/((second/(1-.999**step)).sqrt()+1e-8)
            optimizer.step()
            self.assertTrue(torch.allclose(parameter.double(), expected, rtol=1e-6, atol=1e-7))
        self.assertEqual(optimizer.state[parameter]['step'].item(), 4.)

    def test_optimizer_exact_storage_reload_and_multiple_steps(self):
        import torch
        parameter = torch.nn.Parameter(torch.arange(97, dtype=torch.float32)*.03)
        optimizer = CPUAdamW([parameter], lr=.001, weight_decay=.01)
        parameter.grad = torch.linspace(-1, 1, 97)
        optimizer.step()
        other = torch.nn.Parameter(parameter.detach().clone())
        resumed = CPUAdamW([other], lr=.001, weight_decay=.01)
        from io import BytesIO
        storage = BytesIO()
        torch.save(optimizer.state_dict(), storage)
        storage.seek(0)
        resumed.load_state_dict(torch.load(storage, weights_only=True))
        for _ in range(3):
            parameter.grad = torch.linspace(.25, -.33, 97)
            other.grad = parameter.grad.clone()
            optimizer.step()
            resumed.step()
        self.assertTrue(torch.equal(parameter, other))
        self.assertTrue(all(torch.equal(value, resumed.state[other][name]) for name, value in optimizer.state[parameter].items()))

    def test_optimizer_invalid_later_gradient_leaves_all_state_unchanged(self):
        import torch
        first, second = torch.nn.Parameter(torch.ones(3)), torch.nn.Parameter(torch.ones(4))
        optimizer = CPUAdamW([first, second], lr=.001, weight_decay=.01)
        first.grad, second.grad = torch.ones(3), torch.full((4,), float('nan'))
        with self.assertRaisesRegex(ValueError, 'finite_dense'):
            optimizer.step()
        self.assertTrue(torch.equal(first, torch.ones(3)))
        self.assertFalse(optimizer.state)

    def test_optimizer_none_gradient_and_unsupported_option(self):
        import torch
        parameter = torch.nn.Parameter(torch.ones(3))
        optimizer = CPUAdamW([parameter], lr=.001, weight_decay=.01)
        optimizer.step()
        self.assertTrue(torch.equal(parameter, torch.ones(3)))
        self.assertFalse(optimizer.state)
        optimizer.param_groups[0]['foreach'] = True
        with self.assertRaisesRegex(ValueError, 'explicit_policy'):
            optimizer.step()

    def test_group_stride_padding_dilation_agree_with_double_reference(self):
        import torch
        for groups, stride, padding, dilation in ((1, 1, 0, 1), (2, 2, 1, 1), (4, 1, 2, 2)):
            with self.subTest(groups=groups, stride=stride, dilation=dilation):
                generator = torch.Generator().manual_seed(37)
                inputs = torch.randn(3, 4, 9, 10, generator=generator)
                weight = torch.randn(8, 4//groups, 3, 3, generator=generator, dtype=torch.float64, requires_grad=True)
                output = torch.nn.functional.conv2d(inputs.double(), weight, stride=stride,
                    padding=padding, dilation=dilation, groups=groups)
                outgoing = torch.randn(output.shape, generator=generator)
                output.backward(outgoing.double())
                actual = weight_gradient(inputs, outgoing, weight.shape, stride, padding, dilation, groups)
                self.assertEqual(actual.dtype, torch.float32)
                self.assertTrue(torch.allclose(actual, weight.grad.float(), rtol=1e-6, atol=1e-6))

    def test_native_forward_and_input_gradient_preserved(self):
        import torch
        torch.manual_seed(39)
        first = torch.nn.Conv2d(4, 6, 3, padding=1)
        second = copy.deepcopy(first)
        a = torch.randn(2, 4, 5, 6, requires_grad=True)
        b = a.detach().clone().requires_grad_(True)
        outgoing = torch.randn(2, 6, 5, 6)
        with torch.backends.mkldnn.flags(enabled=False):
            expected = first(a)
            expected.backward(outgoing)
            with cpu_conv_gradients(second):
                actual = second(b)
                actual.backward(outgoing)
        self.assertTrue(torch.equal(expected, actual))
        self.assertTrue(torch.equal(a.grad, b.grad))
        self.assertTrue(torch.equal(first.bias.grad, second.bias.grad))
        self.assertTrue(torch.allclose(first.weight.grad, second.weight.grad, rtol=1e-5, atol=1e-5))
        self.assertFalse(second._forward_hooks)
        self.assertFalse(second.weight._backward_hooks)

    def test_hooks_removed_on_exception_and_no_parameter_mutation(self):
        import torch
        model = torch.nn.Conv2d(2, 3, 1)
        before = copy.deepcopy(model.state_dict())
        with self.assertRaisesRegex(RuntimeError, 'TEST failed backward'):
            with cpu_conv_gradients(model):
                model(torch.randn(1, 2, 4, 4))
                raise RuntimeError('TEST failed backward')
        self.assertFalse(model._forward_hooks)
        self.assertFalse(model.weight._backward_hooks)
        self.assertTrue(all(torch.equal(before[n], value) for n, value in model.state_dict().items()))

    def test_eval_and_frozen_convolutions_are_not_recomputed(self):
        import torch
        from unittest.mock import patch
        model = torch.nn.Conv2d(2, 3, 1).eval()
        with patch('tools.rehab_ml.pose_cpu_gradients.weight_gradient') as calculate:
            with cpu_conv_gradients(model), torch.no_grad():
                model(torch.ones(1, 2, 3, 3))
            calculate.assert_not_called()
        model.train().requires_grad_(False)
        with cpu_conv_gradients(model):
            self.assertFalse(model._forward_hooks)

    def test_shared_forward_without_backward_refused_not_stale_reuse(self):
        import torch
        model = torch.nn.Conv2d(2, 3, 1)
        with cpu_conv_gradients(model):
            model(torch.ones(1, 2, 3, 3))
            with self.assertRaisesRegex(RuntimeError, 'shared_or_invalid'):
                model(torch.ones(1, 2, 3, 3))
        self.assertFalse(model._forward_hooks)

    def test_repeated_batches_release_inputs_and_keep_hooks_bounded(self):
        import torch
        model = torch.nn.Conv2d(2, 3, 1)
        with cpu_conv_gradients(model):
            for _ in range(3):
                model.zero_grad(set_to_none=True)
                model(torch.ones(1, 2, 3, 3)).sum().backward()
                self.assertTrue(torch.isfinite(model.weight.grad).all())
                self.assertEqual(len(model._forward_hooks), 1)
                self.assertEqual(len(model.weight._backward_hooks), 1)
        self.assertFalse(model._forward_hooks)

    def test_policy_rejects_non_float32_and_nonzero_padding(self):
        import torch
        for model in (torch.nn.Conv2d(2, 3, 1).double(),
                      torch.nn.Conv2d(2, 3, 3, padding=1, padding_mode='reflect')):
            with self.assertRaisesRegex(ValueError, 'float32_zero_padding'):
                with cpu_conv_gradients(model):
                    pass
            self.assertFalse(model._forward_hooks)

    def test_wrong_spatial_or_channel_shapes_refused(self):
        import torch
        inputs = torch.zeros(1, 4, 3, 3)
        with self.assertRaisesRegex(ValueError, 'spatial_shape'):
            weight_gradient(inputs, torch.zeros(1, 6, 2, 2), (6, 4, 1, 1), 1, 0, 1, 1)
        with self.assertRaisesRegex(ValueError, 'shapes_required'):
            weight_gradient(inputs, torch.zeros(1, 6, 3, 3), (6, 3, 1, 1), 1, 0, 1, 1)
