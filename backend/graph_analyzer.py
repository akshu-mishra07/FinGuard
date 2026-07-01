from collections import defaultdict
import logging

logger = logging.getLogger("finguard.graph")

class FinguardGraphAnalyzer:
    @staticmethod
    def detect_cycles(recent_transactions, new_sender, new_receiver):
        """
        Detects if adding a directed edge from new_sender to new_receiver forms a cycle
        using transactions within the recent active window.
        
        Returns:
            list: The cycle path as a list of account IDs, or None if no cycle exists.
                  Example: [A, B, C, A]
        """
        # Build adjacency list from recent transactions
        adj_list = defaultdict(list)
        for tx in recent_transactions:
            # tx contains: {"sender": str, "receiver": str}
            sender = tx.get("sender")
            receiver = tx.get("receiver")
            if sender and receiver:
                adj_list[sender].append(receiver)
                
        # To check if new_sender -> new_receiver forms a cycle,
        # we check if there is already a path from new_receiver to new_sender.
        visited = set()
        path = []
        
        def dfs(node, target):
            if node == target:
                path.append(node)
                return True
            if node in visited:
                return False
                
            visited.add(node)
            path.append(node)
            
            for neighbor in adj_list[node]:
                if dfs(neighbor, target):
                    return True
                    
            path.pop()
            return False
            
        if dfs(new_receiver, new_sender):
            # If path exists from receiver to sender, then sender -> receiver completes a cycle.
            # The path returned by dfs will be [receiver, ..., sender].
            # Complete the loop: [sender] + path (which is [sender, receiver, ..., sender])
            full_loop = [new_sender] + path
            return full_loop
            
        return None

    @staticmethod
    def analyze_node_degrees(recent_transactions, account_id):
        """
        Calculates the in-degree, out-degree, and transaction volume for a specific account.
        This represents the localized structure in the network.
        
        Returns:
            dict: {
                "in_degree": int,
                "out_degree": int,
                "unique_senders": list,
                "unique_receivers": list
            }
        """
        senders = set()
        receivers = set()
        
        for tx in recent_transactions:
            sender = tx.get("sender")
            receiver = tx.get("receiver")
            
            if sender == account_id and receiver:
                receivers.add(receiver)
            elif receiver == account_id and sender:
                senders.add(sender)
                
        return {
            "in_degree": len(senders),
            "out_degree": len(receivers),
            "unique_senders": list(senders),
            "unique_receivers": list(receivers)
        }

    @staticmethod
    def check_smurfing_pattern(recent_transactions, account_id, threshold_count=4, max_amount=200.0):
        """
        Detects 'smurfing' or structuring where multiple small transfers flow into a single account,
        often followed by a single large transfer out.
        
        Returns:
            dict: {
                "is_smurfing": bool,
                "smurf_accounts": list,
                "small_tx_count": int
            }
        """
        incoming_txs = []
        outgoing_txs = []
        
        for tx in recent_transactions:
            sender = tx.get("sender")
            receiver = tx.get("receiver")
            amount = tx.get("amount", 0.0)
            
            if receiver == account_id:
                incoming_txs.append((sender, amount))
            elif sender == account_id:
                outgoing_txs.append((receiver, amount))
                
        # Count small incoming transactions
        small_incoming = [sender for sender, amt in incoming_txs if amt <= max_amount]
        unique_small_senders = list(set(small_incoming))
        
        # Check if there's a pattern: many small deposits
        is_smurfing = len(unique_small_senders) >= threshold_count
        
        return {
            "is_smurfing": is_smurfing,
            "smurf_accounts": unique_small_senders,
            "small_tx_count": len(small_incoming)
        }
