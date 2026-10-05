"""The assistant (ADR 0002): a LangGraph agent served over AG-UI to CopilotKit.

Optional (`uv sync --extra agents`). It reads the book through the same
queries as the control room and changes it only through commands, as an
agent actor, after the author says yes. It never decides a gate and never
adopts a version: it prepares, the author decides.
"""
