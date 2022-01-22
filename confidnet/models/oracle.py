import os, sys
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

class Hyperplane(nn.Module):
    """ Inductive Oracle """
    def __init__(self, in_dim, out_dim, temperature=1e-7):
        super(Hyperplane, self).__init__()
        self.linear = nn.Linear(in_dim, out_dim, bias=True)
        self.temperature = temperature

    def forward(self, x, isDistance=True):
        x = self.linear(x) / (torch.pow(self.linear.weight, 2).sum().sqrt()+self.temperature)
        # x = self.linear(x) / (torch.pow(self.linear.weight, 2).sum().sqrt()+self.temperature)
        # if isDistance:
        #     x = self.linear(x) / (torch.pow(self.linear.weight, 2).sum().sqrt()+self.temperature)
        # else:
        #     x = self.linear(x)
        # # x = torch.matmul(x.unsqueeze(1), self.w.unsqueeze(2)) + self.w
        return x