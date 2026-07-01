import asyncio
import random
import logging
from datetime import datetime

logger = logging.getLogger("finguard.simulator")

class FinancialSimulator:
    def __init__(self, submit_transaction_cb):
        self.submit_transaction_cb = submit_transaction_cb
        self.running = False
        self.simulation_task = None
        
        # Predefined account pools for realistic identities
        self.retail_accounts = [f"ACC_RETAIL_{i:04d}" for i in range(1, 101)]
        self.smurf_senders = [f"ACC_SMURF_{i:03d}" for i in range(1, 11)]
        self.mule_accounts = [f"ACC_MULE_{i:03d}" for i in range(1, 11)]
        self.hub_accounts = ["ACC_MERCHANT_HUB", "ACC_OFFSHORE_SHELL"]

    async def start(self):
        if self.running:
            return
        self.running = True
        self.simulation_task = asyncio.create_task(self.run_loop())
        logger.info("Financial simulation engine started.")

    async def stop(self):
        self.running = False
        if self.simulation_task:
            self.simulation_task.cancel()
            try:
                await self.simulation_task
            except asyncio.CancelledError:
                pass
            self.simulation_task = None
        logger.info("Financial simulation engine stopped.")

    async def run_loop(self):
        """
        Continuously generates normal background transactions.
        """
        try:
            while self.running:
                # Generate a normal transaction
                sender = random.choice(self.retail_accounts)
                receiver = random.choice(self.retail_accounts)
                while receiver == sender:
                    receiver = random.choice(self.retail_accounts)
                    
                amount = round(random.uniform(5.0, 150.0) + random.choices([0.0, 100.0, 500.0], weights=[0.85, 0.12, 0.03])[0], 2)
                
                await self.submit_transaction_cb(sender, receiver, amount)
                
                # Sleep a random interval (0.8s to 2.5s)
                await asyncio.sleep(random.uniform(0.8, 2.5))
        except asyncio.CancelledError:
            pass

    async def inject_circular_layering_attack(self, amount=12500.0):
        """
        Injects a circular money-laundering loop: A -> B -> C -> D -> A
        """
        logger.info(f"Injecting Circular Layering Attack with loop amount: ${amount}...")
        
        # Select 4 mule accounts
        mules = random.sample(self.mule_accounts, 4)
        m_a, m_b, m_c, m_d = mules
        
        # Sequence of transactions with small delay
        # Loop: m_a -> m_b -> m_c -> m_d -> m_a
        chain = [(m_a, m_b), (m_b, m_c), (m_c, m_d), (m_d, m_a)]
        
        for idx, (s, r) in enumerate(chain):
            await self.submit_transaction_cb(s, r, amount)
            await asyncio.sleep(0.6) # Short delay to represent streaming nature
            
        logger.info("Circular Layering Attack sequence injected.")

    async def inject_structuring_attack(self, base_amount=150.0):
        """
        Injects a smurfing / structuring attack:
        Many small deposits sent from distinct accounts into a single hub,
        which is then immediately consolidated and sent to an offshore shell.
        """
        logger.info("Injecting Structuring (Smurfing) Attack sequence...")
        
        hub = "ACC_MERCHANT_HUB"
        offshore = "ACC_OFFSHORE_SHELL"
        
        # 1. Multiple small deposits from separate accounts
        senders = random.sample(self.smurf_senders, 6)
        total_mule_inflow = 0.0
        
        for sender in senders:
            # Random amount below standard reporting threshold (e.g. $10,000; here we simulate small smurf transfers)
            amt = round(random.uniform(80.0, 195.0), 2)
            total_mule_inflow += amt
            await self.submit_transaction_cb(sender, hub, amt)
            await asyncio.sleep(0.4)
            
        # 2. immediate large consolidation transfer out
        await asyncio.sleep(1.0)
        consolidation_amt = round(total_mule_inflow, 2)
        await self.submit_transaction_cb(hub, offshore, consolidation_amt)
        
        logger.info(f"Structuring Attack consolidated. Total transferred: ${consolidation_amt}")
