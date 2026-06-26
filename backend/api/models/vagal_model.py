import os
import torch
import torch.nn as nn
import numpy as np
import logging

logger = logging.getLogger(__name__)

class VagalProxyNet(nn.Module):
    """
    2-D CNN matching vagal_proxy_best.pth checkpoint.
    The flat_dim is now passed dynamically to match checkpoint shapes.
    """
    def __init__(self, flat_dim=1536, conv_ch1=32, conv_ch2=64, conv_ch3=128,
                 fc1_out=256, fc2_out=64):
        super().__init__()
        self.conv1 = nn.Conv2d(1, conv_ch1, kernel_size=3, padding=1)
        self.bn1   = nn.BatchNorm2d(conv_ch1)
        self.conv2 = nn.Conv2d(conv_ch1, conv_ch2, kernel_size=3, padding=1)
        self.bn2   = nn.BatchNorm2d(conv_ch2)
        self.conv3 = nn.Conv2d(conv_ch2, conv_ch3, kernel_size=3, padding=1)
        self.bn3   = nn.BatchNorm2d(conv_ch3)
        
        self.pool  = nn.MaxPool2d(2)
        self.relu  = nn.ReLU()
        self.drop  = nn.Dropout(0.3)

        # The dimension mismatch fix: use the flat_dim inferred from the checkpoint
        self.fc1   = nn.Linear(flat_dim, fc1_out)
        self.fc2   = nn.Linear(fc1_out, fc2_out)
        self.fc3   = nn.Linear(fc2_out, 1)

    def forward(self, x):
        # x: (B, 1, H, W)
        x = self.pool(self.relu(self.bn1(self.conv1(x))))
        x = self.pool(self.relu(self.bn2(self.conv2(x))))
        x = self.pool(self.relu(self.bn3(self.conv3(x))))
        
        x = x.flatten(1)
        x = self.drop(self.relu(self.fc1(x)))
        x = self.drop(self.relu(self.fc2(x)))
        return torch.sigmoid(self.fc3(x))


class VagalProxyModel:
    def __init__(self, model_path="./trained_models/vagal_proxy_best.pth"):
        self.model_path = model_path
        self.model      = None
        self.device     = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.is_loaded  = False
        self.input_hw   = 32  # Default assumption for reshaping
        
    def load(self):
        if not os.path.exists(self.model_path):
            logger.warning(f"Checkpoint not found: {self.model_path}")
            return False
        try:
            ckpt = torch.load(self.model_path, map_location=self.device, weights_only=False)

            # Extract state dict
            if isinstance(ckpt, dict) and "model_state_dict" in ckpt:
                sd = ckpt["model_state_dict"]
            else:
                sd = ckpt

            # --- DYNAMIC ARCHITECTURE INFERENCE ---
            conv_ch1 = sd["conv1.weight"].shape[0]
            conv_ch2 = sd["conv2.weight"].shape[0]
            conv_ch3 = sd["conv3.weight"].shape[0]
            
            # This is the 1536 vs 1152 fix:
            flat_dim = sd["fc1.weight"].shape[1] 
            
            fc1_out  = sd["fc1.weight"].shape[0]
            fc2_out  = sd["fc2.weight"].shape[0]

            # Infer input resolution for reshaping in predict()
            # If flat_dim is 1536 and conv_ch3 is 128, spatial area is 12.
            # Assuming a roughly square 3x4 or 4x3 result after 3 pools (8x reduction)
            # we target a 32x32 or similar input.
            spatial_pixels = flat_dim // conv_ch3
            self.input_hw = int((spatial_pixels ** 0.5) * 8) 

            logger.info(f"Loading VagalProxyNet with flat_dim={flat_dim}, target_hw={self.input_hw}")

            self.model = VagalProxyNet(
                flat_dim=flat_dim,
                conv_ch1=conv_ch1, conv_ch2=conv_ch2, conv_ch3=conv_ch3,
                fc1_out=fc1_out, fc2_out=fc2_out
            )
            
            self.model.load_state_dict(sd, strict=True)
            self.model.to(self.device).eval()
            self.is_loaded = True
            return True

        except Exception as exc:
            logger.error(f"Vagal load error: {exc}", exc_info=True)
            return False

    def predict(self, features):
        if not self.is_loaded:
            return {"vagal_score": None, "arousal_level": "unknown"}
            
        try:
            # Convert list/array to tensor
            x = torch.tensor(np.array(features, dtype=np.float32), device=self.device)
            
            # Ensure shape is (B, 1, H, W)
            if x.dim() == 1:
                # If flat, reshape to the inferred HW (e.g., 1, 1, 32, 32)
                x = x.view(1, 1, self.input_hw, -1) 
            elif x.dim() == 2:
                x = x.view(x.shape[0], 1, self.input_hw, -1)

            with torch.no_grad():
                score = self.model(x).item()

            return {
                "vagal_score":    round(score, 4),
                "arousal_level":  self._arousal(score),
                "recommendation": self._rec(score),
            }
        except Exception as exc:
            logger.error(f"Vagal predict error: {exc}")
            return {"vagal_score": None, "arousal_level": "error"}

    @staticmethod
    def _arousal(s):
        return "high" if s < 0.35 else ("medium" if s < 0.65 else "low")

    @staticmethod
    def _rec(s):
        return ("panic_protocol" if s < 0.35 else
                "calm_technique" if s < 0.65 else
                "steady_support")