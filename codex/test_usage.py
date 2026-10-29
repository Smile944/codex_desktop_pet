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
        self.assertEqual(usage_summary(result, now=1793774143-3*86400-5*3600-123),
                         'Codex · 3 天 5 小时额度剩余 75%')

    def test_countdown_changes_with_time_without_new_quota_data(self):
        snapshot = parse_usage(self.sample())
        reset = snapshot['windows'][0]['resetsAt']
        self.assertEqual(usage_summary(snapshot, now=reset-86400),
                         'Codex · 1 天 0 小时额度剩余 75%')
        self.assertEqual(usage_summary(snapshot, now=reset-23*3600),
                         'Codex · 0 天 23 小时额度剩余 75%')

    def test_countdown_less_than_one_hour_and_expired_reset(self):
        snapshot = parse_usage(self.sample())
        reset = snapshot['windows'][0]['resetsAt']
        self.assertEqual(usage_summary(snapshot, now=reset-3599),
                         'Codex · 不足 1 小时额度剩余 75%')
        for now in (reset, reset+60):
            self.assertEqual(usage_summary(snapshot, now=now), 'Codex · 等待额度刷新')

    def test_unknown_reset_does_not_invent_a_countdown(self):
        data = self.sample()
        data['rateLimitsByLimitId']['codex']['primary'].pop('resetsAt')
        self.assertEqual(usage_summary(parse_usage(data), now=1), 'Codex · 7 天额度剩余 75%')

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
