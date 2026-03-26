class TaskProfile:
    name: str
    userid: int
    language: str
    file_path: str
    repeat_type: str
    locale: str
    build_tool: str


class UpdateTaskProfile:
    language: str
    repeat_type: str
    locale: str
    build_tool: str
