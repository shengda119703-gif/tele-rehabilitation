from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class CausalConv(nn.Module):
    def __init__(self, channels, dilation, kernel_size=3):
        super().__init__()
        self.left_padding = dilation*(kernel_size-1)
        self.conv = nn.Conv1d(channels, channels, kernel_size, dilation=dilation)

    def forward(self, value):
        return self.conv(F.pad(value, (self.left_padding, 0)))


class ResidualBlock(nn.Module):
    def __init__(self, channels, dilation, dropout):
        super().__init__()
        self.layers = nn.ModuleList([CausalConv(channels, dilation) for _ in range(2)])
        # Normalize only feature channels of EACH timestep, never time/batch statistics.
        self.norms = nn.ModuleList([nn.LayerNorm(channels) for _ in range(2)])
        self.dropout = nn.Dropout(dropout)

    def forward(self, value):
        current = value
        for conv, norm in zip(self.layers, self.norms):
            current = conv(current)
            current = norm(current.transpose(1, 2)).transpose(1, 2)
            current = self.dropout(F.gelu(current))
        return value+current


class CausalTCN(nn.Module):
    receptive_field_steps = 61

    def __init__(self, input_dim, channels=64, dropout=.1):
        super().__init__()
        self.project = nn.Conv1d(input_dim, channels, 1)
        self.blocks = nn.ModuleList([ResidualBlock(channels, dilation, dropout) for dilation in (1, 2, 4, 8)])
        self.head = nn.Linear(channels, 2)

    def encode(self, features):
        value = self.project(features.transpose(1, 2))
        for block in self.blocks:
            value = block(value)
        return value.transpose(1, 2)

    def forward(self, features, padding_mask):
        hidden = self.encode(features)
        valid = padding_mask.unsqueeze(-1).to(hidden.dtype)
        pooled = (hidden*valid).sum(1)/valid.sum(1).clamp_min(1.)
        return self.head(pooled)


def masked_cross_entropy(logits, labels, label_mask, weights=None):
    valid = label_mask.bool()
    if not valid.any():
        # Zero loss connected to the graph; absent labels never become class 0.
        return logits.sum()*0.
    return F.cross_entropy(logits[valid], labels[valid], weight=weights)
