import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta

logger = logging.getLogger("finguard.db")

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = "finguard"

class FinguardDatabase:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        logger.info(f"Connecting to MongoDB at {MONGODB_URI}...")
        self.client = AsyncIOMotorClient(MONGODB_URI)
        self.db = self.client[DB_NAME]
        
        # Setup indexes
        await self.db.transactions.create_index("timestamp")
        await self.db.transactions.create_index([("sender", 1), ("timestamp", -1)])
        await self.db.transactions.create_index([("receiver", 1), ("timestamp", -1)])
        await self.db.identities.create_index("account_id", unique=True)
        logger.info("MongoDB connection and index creation complete.")

    async def close(self):
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed.")

    async def insert_transaction(self, tx_doc):
        """
        Inserts a single transaction record.
        """
        tx_doc["created_at"] = datetime.utcnow()
        result = await self.db.transactions.insert_one(tx_doc)
        return str(result.inserted_id)

    async def get_recent_transactions(self, window_minutes=10):
        """
        Fetches all transactions from the last N minutes to build the active linkage graph.
        """
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        cursor = self.db.transactions.find({"timestamp": {"$gte": cutoff}})
        txs = []
        async for doc in cursor:
            # Convert object ids to string
            doc["_id"] = str(doc["_id"])
            if isinstance(doc.get("timestamp"), datetime):
                # keep as datetime, but standard output will serialize it
                pass
            txs.append(doc)
        return txs

    async def get_account_recent_transactions(self, account_id, window_minutes=10):
        """
        Gets recent transactions where the account_id was sender or receiver.
        """
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        cursor = self.db.transactions.find({
            "$and": [
                {"timestamp": {"$gte": cutoff}},
                {"$or": [{"sender": account_id}, {"receiver": account_id}]}
            ]
        })
        txs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            txs.append(doc)
        return txs

    async def update_identity_cache(self, account_id, metrics):
        """
        Dynamically caches user risk velocity metrics and polymorphic transacting parameters.
        `metrics` includes rolling window totals, transaction counts, current risk score, etc.
        """
        await self.db.identities.update_one(
            {"account_id": account_id},
            {
                "$set": {
                    "last_updated": datetime.utcnow(),
                    **metrics
                }
            },
            upsert=True
        )

    async def get_identity(self, account_id):
        """
        Fetches cached risk velocity profile for an account.
        """
        doc = await self.db.identities.find_one({"account_id": account_id})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    async def get_all_identities(self):
        """
        Fetches all cached risk velocity profiles.
        """
        cursor = self.db.identities.find()
        identities = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            identities.append(doc)
        return identities

    async def clear_database(self):
        """
        Clears the transaction ledger and cached identities.
        """
        await self.db.transactions.delete_many({})
        await self.db.identities.delete_many({})
        logger.info("Database transaction and identity collections cleared.")
