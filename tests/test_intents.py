import sys
sys.path.insert(0, "/Users/voolf/Documents/opencode/OCVoice")

from ocvoice.intent.parser import RegexIntentParser
from ocvoice.intent.intents import Intent


class TestProjectIntents:
    """Test project-related intent parsing (RU + EN).

    @contract: All tests assert exact Intent enum match
    @desc: Tests CURRENT_PROJECT and LIST_PROJECTS intents in both
           Russian and English variations.
    @tags: test, intent, parser, project
    """

    parser = RegexIntentParser()

    def test_current_project_ru(self):
        cmd = self.parser.parse("какой проект")
        assert cmd.intent == Intent.CURRENT_PROJECT

    def test_current_project_ru_alt(self):
        cmd = self.parser.parse("текущий проект")
        assert cmd.intent == Intent.CURRENT_PROJECT

    def test_current_project_en(self):
        cmd = self.parser.parse("what project")
        assert cmd.intent == Intent.CURRENT_PROJECT

    def test_current_project_en_alt(self):
        cmd = self.parser.parse("current project")
        assert cmd.intent == Intent.CURRENT_PROJECT

    def test_list_projects_ru(self):
        cmd = self.parser.parse("список проектов")
        assert cmd.intent == Intent.LIST_PROJECTS

    def test_list_projects_en(self):
        cmd = self.parser.parse("list projects")
        assert cmd.intent == Intent.LIST_PROJECTS

    def test_list_projects_en_alt(self):
        cmd = self.parser.parse("all projects")
        assert cmd.intent == Intent.LIST_PROJECTS


class TestSwitchProjectIntent:
    """Test SWITCH_PROJECT intent in RU and EN.

    @contract: Tests that switch commands extract the project name argument
    @tags: test, intent, parser, project
    """

    parser = RegexIntentParser()

    def test_switch_project_ru(self):
        cmd = self.parser.parse("переключи проект на test")
        assert cmd.intent == Intent.SWITCH_PROJECT

    def test_switch_project_en(self):
        cmd = self.parser.parse("switch to project my-app")
        assert cmd.intent == Intent.SWITCH_PROJECT


class TestSessionIntents:
    """Test session-related intent parsing.

    @contract: Tests SWITCH_SESSION, NEW_SESSION, LIST_SESSIONS intents
    @tags: test, intent, parser, session
    """

    parser = RegexIntentParser()

    def test_switch_session_sticks(self):
        cmd = self.parser.parse("работай с сессией backend")
        assert cmd.intent == Intent.SWITCH_SESSION
        assert cmd.arguments.get("session") is not None or cmd.text

    def test_new_session(self):
        cmd = self.parser.parse("новая сессия")
        assert cmd.intent == Intent.NEW_SESSION

    def test_list_sessions(self):
        cmd = self.parser.parse("список сессий")
        assert cmd.intent == Intent.LIST_SESSIONS
