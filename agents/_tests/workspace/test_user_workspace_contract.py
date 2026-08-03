import inspect
import unittest

from agents._application.workspace.service import load_user_workspace


class UserWorkspaceContractTests(unittest.TestCase):
    def test_user_workspace_contract_has_no_conversation_parameter(self):
        parameters = inspect.signature(load_user_workspace).parameters

        self.assertEqual(tuple(parameters), ("store", "user_id"))
        self.assertEqual(
            parameters["user_id"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )


if __name__ == "__main__":
    unittest.main()
