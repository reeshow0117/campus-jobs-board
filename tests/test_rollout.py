import unittest
from scripts.rollout_server import preserve_admin_extensions


class PreserveExtensionsTests(unittest.TestCase):
    def test_admin_routes_and_capability_survive_without_old_generation(self):
        old = '''"""old"""
import hmac
ADMIN_TOKEN = "synthetic"
def capabilities():
    return {"llm": False, "admin_invite": bool(ADMIN_TOKEN)}
def require_admin(request):
    return hmac.compare_digest(request, ADMIN_TOKEN)
def admin_page():
    return "admin"
def gen_resume():
    return "old"
'''
        new = '''"""new"""
def capabilities():
    return {"llm": True}
def gen_resume():
    return "new"
'''
        merged, names = preserve_admin_extensions(old, new)
        scope = {}
        exec(merged, scope)
        self.assertEqual("new", scope["gen_resume"]())
        self.assertEqual({"llm": True, "admin_invite": True}, scope["capabilities"]())
        self.assertTrue(scope["require_admin"]("synthetic"))
        self.assertFalse(scope["require_admin"]("wrong"))
        self.assertEqual({"require_admin", "admin_page"}, set(names))

    def test_unreviewed_server_extension_stops_rollout(self):
        with self.assertRaisesRegex(ValueError, "未审阅"):
            preserve_admin_extensions("def other_extension(): pass", "")
