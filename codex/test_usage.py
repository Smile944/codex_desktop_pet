import unittest
from usage import parse_usage, usage_summary, read_usage


class UsageTests(unittest.TestCase):
    def sample(self):
        return {'rateLimitsByLimitId': {'codex': {
            'planType': 'pro', 'primary': {'usedPercent': 25, 'windowDurationMins': 10080, 'resetsAt': 1793774143},
            'secondary': None, 'credits': {'balance': '123.4000', 'unlimited': False}}}}

    def test_real_quota_percentages_and_reset_time(self):
        result = parse_usage(self.sample())
        self.assertEqual(result['windows'][0]['remainingPercent'], 75)
        self.assertEqual(result['windows'][0]['resetsAt'], 1793774143)
        self.assertEqual(result['planType'], 'pro')
        self.assertEqual(result['creditsBalance'], '123.4000')
        self.assertEqual(usage_summary(result), 'Codex · 7 天额度剩余 75%')

    def test_missing_is_unknown_not_zero_and_invalid_windows_ignored(self):
        result = parse_usage({'rateLimits': {'primary':None,'secondary':None}})
        self.assertEqual(result['windows'], [])
        self.assertIsNone(result['creditsBalance'])
        self.assertIn('未提供', usage_summary(result))
        result = parse_usage({'rateLimits': {'primary':{'usedPercent':True},'secondary':{'usedPercent':float('nan')}}})
        self.assertEqual(result['windows'], [])

    def test_multi_bucket_and_percentage_clamping(self):
        data = self.sample()
        data['rateLimitsByLimitId']['other'] = {'primary':{'usedPercent':110, 'windowDurationMins':300}}
        result = parse_usage(data)
        self.assertEqual(len(result['windows']), 2)
        self.assertEqual(result['windows'][1]['remainingPercent'], 0)

    def test_real_rollout_snake_case_fields(self):
        result = parse_usage({'rateLimits': {'limit_id':'codex','primary':{
            'used_percent':25,'window_minutes':10080,'resets_at':1793774143},'secondary':None}})
        self.assertEqual(result['windows'][0]['remainingPercent'], 75)
        self.assertEqual(result['windows'][0]['resetsAt'], 1793774143)

    def test_rpc_only_initializes_and_reads_limits(self):
        calls = []
        def fake_rpc(method, params=None):
            calls.append(method)
            return self.sample() if method == 'account/rateLimits/read' else {}
        result = read_usage(rpc=fake_rpc)
        self.assertEqual(calls, ['initialize', 'initialized', 'account/rateLimits/read'])
        self.assertEqual(result['windows'][0]['remainingPercent'], 75)


if __name__ == '__main__':
    unittest.main()
