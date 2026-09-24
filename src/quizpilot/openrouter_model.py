"""OpenRouter model compatibility settings used by QuizPilot."""

from langchain_openrouter import ChatOpenRouter


class QuizPilotOpenRouter(ChatOpenRouter):
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        # Use one policy across OpenRouter models: let the model choose its tool,
        # then enforce allowed calls and structured results in the application.
        # Some providers return tool syntax as text when tool choice is forced.
        if tool_choice == "any":
            tool_choice = "auto"
        return super().bind_tools(tools, tool_choice=tool_choice, **kwargs)
