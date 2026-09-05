"""
v1.19.7: LLM 返回 JSON 的统一解析入口

此前项目内有 3 套健壮度不一的实现（analyzer._extract_json 最强、
pipelines._extract_json_from_text 中等、weekly_report._parse_ai_json 最弱），
周/月/年报恰好用的是最弱版本——AI 在 JSON 前后多输出一段文字即解析失败，
产出入库一份全空字段的"成功"报告。本模块合并为单一实现，
各旧函数名保留为薄委托，调用方无需改动。
"""
import json
import logging
import re

logger = logging.getLogger(__name__)


def repair_json_text(text: str) -> str:
    """修复 LLM 生成 JSON 时的常见格式错误"""
    # 1. 尾随逗号：对象 {a:1,} 或数组 [1,2,]
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)

    # 2. 连续逗号：{a:1,,b:2} → {a:1,b:2}
    text = re.sub(r',\s*,', ',', text)

    # 3. 字符串值内部的未转义双引号（常见于 quote 内容）
    #    模式："quote": "他说"你好"世界" → 把内层引号替换为中文引号
    #    这是一个启发式修复，在 key: 后面的字符串值中进行
    def _fix_inner_quotes(m):
        key = m.group(1)
        value = m.group(2)
        # 把内部的英文双引号替换为中文引号（交替左右引号）
        result = []
        in_quote = False
        for ch in value:
            if ch == '"':
                if not in_quote:
                    result.append('“')  # "
                    in_quote = True
                else:
                    result.append('”')  # "
                    in_quote = False
            else:
                result.append(ch)
        return f'"{key}": "{"".join(result)}"'

    text = re.sub(r'"(\w+)":\s*"([^"]*?)"', _fix_inner_quotes, text)

    # 4. 单引号 JSON → 双引号（仅处理 key 和明显的 value）
    #    保守策略：只替换 key 层面的单引号
    #    （value 中可能包含合法单引号如 "I'm"，不处理）

    return text


def parse_llm_json(raw_data) -> dict | None:
    """从 AI 返回内容中提取 JSON 对象。

    处理各种情况：纯 JSON / Markdown 代码块包裹 / JSON 前后有杂文 /
    LLM 常见格式错误（尾随逗号、未转义引号等）/ 全角符号。

    Args:
        raw_data: AI 返回的 str，或已经解析好的 dict

    Returns:
        dict：解析成功
        None：无法解析或顶层数组非对象——调用方应视为 AI 失败，
              而不是当作空数据继续走入库流程
    """
    if isinstance(raw_data, dict):
        return raw_data
    if not isinstance(raw_data, str) or not raw_data.strip():
        return None

    text = raw_data.strip()

    # 预处理：全角符号 → 半角
    text = text.replace("｛", "{").replace("｝", "}")
    text = text.replace("［", "[").replace("］", "]")
    text = text.replace("：", ":").replace("，", ",")

    # v1.19.7: 保留补括号前的文本——下方"补缺失括号"会在杂文包裹场景
    # 伪造出首字符 '{'，导致尝试 4 的截取搜索从假括号开始而全部失败
    raw_text = text

    # 补缺失的开头 {
    if text and text[0] not in "{[":
        text = "{" + text
    # 补缺失的结尾 }
    if text and text[-1] not in "}]":
        text = text + "}"

    def _as_dict(data):
        return data if isinstance(data, dict) else None

    # 尝试 1：直接解析
    try:
        return _as_dict(json.loads(text))
    except json.JSONDecodeError:
        pass

    # 尝试 2：修复后解析
    try:
        return _as_dict(json.loads(repair_json_text(text)))
    except json.JSONDecodeError:
        pass
    except Exception as e:
        logger.debug("JSON 修复解析异常: %s", e)

    # 尝试 3：提取 Markdown 代码块 ```json ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        block = m.group(1).strip()
        try:
            return _as_dict(json.loads(block))
        except json.JSONDecodeError:
            try:
                return _as_dict(json.loads(repair_json_text(block)))
            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.debug("JSON 代码块修复解析异常: %s", e)

    # 尝试 4：找到第一个 {，然后从后往前找 }，逐步缩短直到解析成功（基于原文搜索）
    start = raw_text.find("{")
    if start != -1:
        end = raw_text.rfind("}")
        while end > start:
            try:
                return _as_dict(json.loads(raw_text[start:end + 1]))
            except json.JSONDecodeError:
                try:
                    return _as_dict(json.loads(repair_json_text(raw_text[start:end + 1])))
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    logger.debug("JSON 截取修复解析异常: %s", e)
            end = raw_text.rfind("}", start, end)  # 往前找上一个 }

    return None
