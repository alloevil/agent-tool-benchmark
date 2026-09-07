"""计算器 🧮 helpers with 多字节 characters."""

GREETING = "你好,世界 👋"


def describe(op):
    # 返回操作的中文描述 📝
    names = {
        "add": "加法 ➕",
        "sub": "减法 ➖",
    }
    return names.get(op, "未知 ❓")


def format_result(value):
    if value == float("inf"):
        return "结果 → ∞ ♾️"
    return f"结果 → {value} ✅"


def banner():
    return "═" * 20 + " 计算完成 🎉 " + "═" * 20
