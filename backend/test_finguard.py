import sys
import unittest
import torch
import numpy as np

# Add backend directory to path to import components
from ai_model import FinguardAIEnsemble
from graph_analyzer import FinguardGraphAnalyzer

class TestFinguardComponents(unittest.TestCase):
    def test_pytorch_autoencoder_and_ensemble(self):
        """
        Verify that PyTorch Autoencoder and Isolation Forest can be trained and run inference.
        """
        print("Testing ML ensemble fitting...")
        ensemble = FinguardAIEnsemble(input_dim=8, latent_dim=4)
        
        # Fit model on synthetic data
        ensemble.fit(epochs=5) # few epochs for speed
        self.assertTrue(ensemble.is_trained, "Ensemble model failed to train.")
        
        # Test predictions
        print("Testing ML predictions...")
        # Normal profile: [amount, velocity_1m, velocity_10m, freq_1m, freq_10m, out_deg, in_deg, loop]
        normal_tx = [50.0, 100.0, 400.0, 2.0, 4.0, 1.0, 1.0, 0.0]
        prediction_normal = ensemble.predict(normal_tx)
        
        # Anomaly profile: very high amount, velocities, frequencies, and loop involvement
        anomaly_tx = [50000.0, 80000.0, 150000.0, 20.0, 50.0, 8.0, 12.0, 1.0]
        prediction_anomaly = ensemble.predict(anomaly_tx)
        
        print(f"Normal Transaction Prediction: {prediction_normal}")
        print(f"Anomaly Transaction Prediction: {prediction_anomaly}")
        
        # Check that risk score is higher for anomaly
        self.assertGreater(prediction_anomaly["risk_score"], prediction_normal["risk_score"], 
                           "Anomaly risk score should be greater than normal risk score.")
        self.assertTrue(prediction_anomaly["is_anomaly"], "High-risk transaction should be flagged as anomaly.")

    def test_cycle_detection(self):
        """
        Verify that directed cycles (money-laundering loops) are correctly identified by the Graph Analyzer.
        """
        print("Testing cycle detection logic...")
        # Mock recent transactions
        recent_txs = [
            {"sender": "A", "receiver": "B"},
            {"sender": "B", "receiver": "C"},
            {"sender": "C", "receiver": "D"},
        ]
        
        # Adding edge A -> B: already exists, does not complete cycle receiver -> sender
        # Adding edge D -> A: creates cycle A -> B -> C -> D -> A
        cycle = FinguardGraphAnalyzer.detect_cycles(recent_txs, "D", "A")
        print(f"Detected Cycle: {cycle}")
        
        self.assertIsNotNone(cycle, "Cycle D -> A -> B -> C -> D should be detected.")
        self.assertEqual(cycle, ["D", "A", "B", "C", "D"], "Detected cycle path is incorrect.")
        
        # Adding edge D -> B: creates cycle B -> C -> D -> B
        cycle_db = FinguardGraphAnalyzer.detect_cycles(recent_txs, "D", "B")
        self.assertEqual(cycle_db, ["D", "B", "C", "D"], "Detected cycle D -> B -> C -> D is incorrect.")
        
        # Adding edge A -> D: does not create a cycle since graph is directed A -> B -> C -> D
        no_cycle = FinguardGraphAnalyzer.detect_cycles(recent_txs, "A", "D")
        self.assertIsNone(no_cycle, "No cycle should be detected for A -> D.")

    def test_smurfing_pattern(self):
        """
        Verify that structuring (smurfing) pattern is correctly identified by the Graph Analyzer.
        """
        print("Testing structuring (smurfing) detection...")
        # Hub account receives many small transactions
        hub = "HUB_ACCOUNT"
        recent_txs = [
            {"sender": "S1", "receiver": hub, "amount": 100.0},
            {"sender": "S2", "receiver": hub, "amount": 120.0},
            {"sender": "S3", "receiver": hub, "amount": 90.0},
            {"sender": "S4", "receiver": hub, "amount": 110.0},
        ]
        
        smurfing = FinguardGraphAnalyzer.check_smurfing_pattern(recent_txs, hub, threshold_count=4, max_amount=150.0)
        print(f"Smurfing Analysis: {smurfing}")
        
        self.assertTrue(smurfing["is_smurfing"], "Structuring smurf pattern should be detected.")
        self.assertEqual(smurfing["small_tx_count"], 4, "Number of small deposits should be 4.")
        self.assertIn("S1", smurfing["smurf_accounts"], "S1 should be identified as a smurf sender.")

if __name__ == "__main__":
    unittest.main()
