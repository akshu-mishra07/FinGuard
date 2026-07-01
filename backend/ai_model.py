import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import logging

logger = logging.getLogger("finguard.ai")

class TransactionAutoencoder(nn.Module):
    def __init__(self, input_dim=8, latent_dim=4):
        super().__init__()
        # Encoder: compress high-dimensional transaction metrics into bottleneck latent space
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 8),
            nn.ReLU(),
            nn.Linear(8, latent_dim)
        )
        # Decoder: reconstruct original features from latent space
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 8),
            nn.ReLU(),
            nn.Linear(8, 16),
            nn.ReLU(),
            nn.Linear(16, input_dim)
        )

    def forward(self, x):
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        return reconstructed, latent


class FinguardAIEnsemble:
    def __init__(self, input_dim=8, latent_dim=4):
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.scaler = StandardScaler()
        self.autoencoder = TransactionAutoencoder(input_dim, latent_dim)
        self.isolation_forest = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
        self.is_trained = False
        
        # Scaling parameters for MSE to map to [0, 1] risk score
        self.ae_score_alpha = 1.5

    def generate_synthetic_normal_data(self, n_samples=2000):
        """
        Generates synthetic transaction behavior representing normal activity:
        Features:
        0: amount (normally distributed, mean=$50, std=$30, bounded positive)
        1: velocity_1m (sum of amounts last minute: mean=$150, std=$80)
        2: velocity_10m (sum of amounts last 10 minutes: mean=$800, std=$300)
        3: frequency_1m (number of tx last minute: mean=1.5, std=0.8)
        4: frequency_10m (number of tx last 10 minutes: mean=5, std=2)
        5: sender_out_degree (unique receivers: mean=1.2, std=0.5)
        6: receiver_in_degree (unique senders: mean=1.5, std=0.7)
        7: loop_involvement (normally 0 for normal accounts)
        """
        np.random.seed(42)
        
        amounts = np.random.normal(50, 30, n_samples)
        amounts = np.clip(amounts, 1.0, 1000.0)
        
        velocity_1m = amounts * np.random.uniform(1.0, 3.0, n_samples)
        velocity_10m = velocity_1m * np.random.uniform(3.0, 6.0, n_samples)
        
        freq_1m = np.random.poisson(1.5, n_samples)
        freq_1m = np.clip(freq_1m, 1, 5)
        
        freq_10m = freq_1m * np.random.randint(2, 6, n_samples)
        
        out_deg = np.random.poisson(1.2, n_samples)
        out_deg = np.clip(out_deg, 1, 4)
        
        in_deg = np.random.poisson(1.5, n_samples)
        in_deg = np.clip(in_deg, 1, 5)
        
        loop = np.zeros(n_samples)
        
        data = np.stack([
            amounts,
            velocity_1m,
            velocity_10m,
            freq_1m.astype(float),
            freq_10m.astype(float),
            out_deg.astype(float),
            in_deg.astype(float),
            loop
        ], axis=1)
        
        return data

    def fit(self, data=None, epochs=20, batch_size=64):
        """
        Train the PyTorch Autoencoder and fit scikit-learn Isolation Forest on baseline dataset.
        """
        logger.info("Initializing baseline training for AML transaction screening models...")
        if data is None:
            data = self.generate_synthetic_normal_data()
            
        # Fit scaler
        scaled_data = self.scaler.fit_transform(data)
        
        # Train Autoencoder
        x_tensor = torch.tensor(scaled_data, dtype=torch.float32)
        optimizer = optim.Adam(self.autoencoder.parameters(), lr=0.01)
        criterion = nn.MSELoss()
        
        self.autoencoder.train()
        for epoch in range(epochs):
            permutation = torch.randperm(x_tensor.size()[0])
            epoch_loss = 0.0
            for i in range(0, x_tensor.size()[0], batch_size):
                indices = permutation[i:i+batch_size]
                batch_x = x_tensor[indices]
                
                optimizer.zero_grad()
                reconstructed, _ = self.autoencoder(batch_x)
                loss = criterion(reconstructed, batch_x)
                loss.backward()
                optimizer.step()
                
                epoch_loss += loss.item() * batch_x.size(0)
            
            avg_loss = epoch_loss / x_tensor.size(0)
            if (epoch + 1) % 5 == 0:
                logger.info(f"Autoencoder Epoch {epoch+1}/{epochs} | Reconstruction Loss: {avg_loss:.6f}")
                
        # Fit Isolation Forest
        self.isolation_forest.fit(scaled_data)
        
        # Evaluate baseline MSE for scaling purposes
        self.autoencoder.eval()
        with torch.no_grad():
            reconstructed, _ = self.autoencoder(x_tensor)
            mses = torch.mean((reconstructed - x_tensor)**2, dim=1).numpy()
            self.baseline_mean_mse = float(np.mean(mses))
            self.baseline_std_mse = float(np.std(mses))
            
        self.is_trained = True
        logger.info("Ensemble models trained successfully.")

    def predict(self, feature_list):
        """
        Runs real-time inference on a transaction's feature list.
        Returns:
            dict: {
                "risk_score": float (0.0 to 1.0),
                "ae_mse": float,
                "if_score": float,
                "is_anomaly": bool
            }
        """
        if not self.is_trained:
            logger.warning("Models not pre-trained. Auto-fitting on synthetic data...")
            self.fit()
            
        feat_arr = np.array(feature_list).reshape(1, -1)
        scaled_feat = self.scaler.transform(feat_arr)
        
        # 1. PyTorch Autoencoder Evaluation
        self.autoencoder.eval()
        feat_tensor = torch.tensor(scaled_feat, dtype=torch.float32)
        with torch.no_grad():
            reconstructed, _ = self.autoencoder(feat_tensor)
            mse = float(torch.mean((reconstructed - feat_tensor)**2).item())
            
        # Map MSE to 0-1 scale using exponential CDF logic
        # Standardize MSE relative to baseline normal
        standardized_mse = (mse - self.baseline_mean_mse) / (self.baseline_std_mse + 1e-8)
        standardized_mse = max(0.0, standardized_mse)
        ae_risk_score = float(1.0 - np.exp(-standardized_mse * self.ae_score_alpha))
        
        # 2. Isolation Forest Evaluation
        # decision_function outputs negative values for anomalies, positive for normal
        if_decision = float(self.isolation_forest.decision_function(scaled_feat)[0])
        # Map to 0-1 risk score (lower decision -> higher risk)
        # Typically runs from -0.5 to 0.5. We scale it so that negative represents high risk.
        if_risk_score = float(1.0 / (1.0 + np.exp(15.0 * (if_decision + 0.05))))
        
        # 3. Ensemble Fusion
        # We take the maximum score to ensure that if either the structural loop / density forest
        # or the vector shift autoencoder spots an anomaly, the alert gets flagged.
        combined_risk_score = float(max(ae_risk_score, if_risk_score))
        
        # If combined risk is high or structural anomalies present
        is_anomaly = combined_risk_score > 0.65
        
        return {
            "risk_score": round(combined_risk_score, 4),
            "ae_mse": round(mse, 6),
            "if_score": round(if_decision, 6),
            "is_anomaly": is_anomaly
        }
