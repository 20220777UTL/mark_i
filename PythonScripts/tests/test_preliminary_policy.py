import unittest
from Play.Normal.PreliminaryPolicy import Frame, Robot, PreliminaryPolicy


def frame(t=0, ball=(0, 0), ours=None, enemies=None, valid=True):
    return Frame(t, ball, (0, 0), ours or {1: Robot(-100, 0, infrared=True), 2: Robot(650, -850)},
                 enemies or {0: Robot(4320, 0)}, valid)


class PolicyTests(unittest.TestCase):
    def test_nearest_selected_and_roles_stable(self):
        p = PreliminaryPolicy()
        p.tick(frame())
        self.assertEqual(p.attacker, 1)
        p.tick(frame(.05, ours={1: Robot(-300, 0), 2: Robot(-50, 0)}))
        self.assertEqual(p.attacker, 1)

    def test_other_robot_can_be_selected(self):
        p = PreliminaryPolicy()
        p.tick(frame(ours={1: Robot(-900, 0), 2: Robot(-100, 0)}))
        self.assertEqual(p.attacker, 2)

    def test_missing_vision_stops_both(self):
        p = PreliminaryPolicy()
        actions = p.tick(frame(valid=False))
        self.assertEqual(set(actions), {1, 2})
        self.assertTrue(all(a.kind == "stop" for a in actions.values()))

    def test_penalty_ball_not_chased(self):
        for x in (-3600, 3600, 4600):
            self.assertTrue(all(a.kind == "stop" for a in PreliminaryPolicy().tick(frame(ball=(x, 0))).values()))

    def test_carry_limit_stops(self):
        p = PreliminaryPolicy()
        p.tick(frame())
        p.carry = 821
        self.assertTrue(all(a.kind == "stop" for a in p.tick(frame(.2)).values()))

    def test_does_not_wait_forever_for_keeper(self):
        p = PreliminaryPolicy()
        p.tick(frame())
        p.tick(frame(.2))
        p.tick(frame(2))
        self.assertEqual(p.phase, "pass")
        self.assertIn("time limit", p.reason)

    def test_blocked_pass_not_kicked(self):
        p = PreliminaryPolicy()
        p.tick(frame())
        p.phase = "pass"
        p.pass_origin, p.pass_target = (0, 0), (650, -850)
        actions = p.tick(frame(.2, enemies={0: Robot(325, -425)}))
        self.assertNotEqual(actions[1].kind, "kick")

    def test_receive_changes_carrier_and_resets_budget(self):
        p = PreliminaryPolicy()
        p.tick(frame())
        p.phase = "receive"
        p.carry = 600
        p.tick(frame(.2, ball=(2200, -850), ours={1: Robot(1500, 600), 2: Robot(2100, -850, infrared=True)}))
        self.assertEqual((p.attacker, p.receiver, p.phase, p.carry), (2, 1, "shoot", 0))


if __name__ == "__main__":
    unittest.main()
