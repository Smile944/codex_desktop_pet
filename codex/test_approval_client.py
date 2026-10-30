"""The manual verification client must never silently approve a request."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).parent/'verification'))
from manual_decline import ApprovalGate


class ManualApprovalTests(unittest.TestCase):
    def test_no_decision_until_human_action_and_accept_is_forbidden(self):
        sent=[]
        gate=ApprovalGate(sent.append)
        gate.receive({'id':8,'method':'item/commandExecution/requestApproval','params':{
            'threadId':'t','turnId':'u','command':'printf TEST','availableDecisions':['decline','cancel']}})
        self.assertEqual(sent,[])
        with self.assertRaises(ValueError):gate.decide(8,'accept')
        self.assertEqual(sent,[])
        gate.decide(8,'decline')
        self.assertEqual(sent,[{'id':8,'result':{'decision':'decline'}}])
        with self.assertRaises(ValueError):gate.decide(8,'cancel')

    def test_stale_click_or_unsupported_decision_does_not_resolve_request(self):
        sent=[];gate=ApprovalGate(sent.append)
        gate.receive({'id':9,'method':'item/commandExecution/requestApproval','params':{
            'availableDecisions':['cancel'],'command':'printf TEST'}})
        for request,decision in ((8,'cancel'),(9,'decline')):
            with self.assertRaises(ValueError):gate.decide(request,decision)
        self.assertEqual(sent,[])
        gate.decide(9,'cancel')
        self.assertEqual(sent[0]['result'],{'decision':'cancel'})

    def test_server_resolution_invalidates_only_the_matching_request(self):
        sent=[];gate=ApprovalGate(sent.append)
        gate.receive({'id':9,'method':'item/commandExecution/requestApproval','params':{}})
        gate.resolve(8)
        self.assertIsNotNone(gate.pending)
        gate.resolve(9)
        with self.assertRaises(ValueError):gate.decide(9,'decline')
        self.assertEqual(sent,[])
        self.assertIsNone(gate.decision)
