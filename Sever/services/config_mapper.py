"""
配置映射服务层。

将数据库中的模型配置和提示词配置映射到 config.py 中的变量。
基于命名约定自动映射。
"""

import sys
import os

from typing import Any, Dict, Optional

from services import config_service


LLM_USAGE_PREFIXES = (
    "theme_select",
    "org",
    "summary",
    "summary_limit",
    "summary_batch",
    "idea_generate",
    "idea_ingest",
    "idea_question",
    "idea_candidate",
    "idea_review",
    "idea_revise",
    "idea_plan",
    "idea_eval",
)

_API_KEY_MAPPING = {
    "theme_select": "qwen_api_key",
    "org": "qwen_api_key",
    "summary": "qwen_api_key",
    "summary_limit": "qwen_api_key",
    "summary_batch": "summary_batch_api_key",
    "idea_generate": "idea_generate_api_key",
    "idea_ingest": "idea_ingest_api_key",
    "idea_question": "idea_question_api_key",
    "idea_candidate": "idea_candidate_api_key",
    "idea_review": "idea_review_api_key",
    "idea_revise": "idea_revise_api_key",
    "idea_plan": "idea_plan_api_key",
    "idea_eval": "idea_eval_api_key",
}

# 懒加载 config 模块引用，用于在映射时检查目标变量是否存在
def _get_config_module():
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _base not in sys.path:
        sys.path.insert(0, _base)
    import config.config as _cfg
    return _cfg


def map_llm_config_to_variables(config: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    """根据前缀将模型配置映射到config.py变量。
    
    映射规则：候选字段必须在 config.py 中实际存在才会写入，
    不存在的变量自动跳过（避免因各前缀支持的字段不同而报错）。
    
    Args:
        config: 模型配置字典（来自数据库）
        prefix: 使用前缀（如 "theme_select", "org", "summary" 等）
        
    Returns:
        映射后的变量字典，可直接用于 config_service.update_config
    """
    updates = {}
    cfg_module = _get_config_module()

    # 完整候选字段映射：仅当 config.py 中存在对应变量时才生效
    field_mapping = {
        "base_url": f"{prefix}_base_url",
        "model": f"{prefix}_model",
        "max_tokens": f"{prefix}_max_tokens",
        "temperature": f"{prefix}_temperature",
        "concurrency": f"{prefix}_concurrency",
        "input_hard_limit": f"{prefix}_input_hard_limit",
        "input_safety_margin": f"{prefix}_input_safety_margin",
        "use_openrouter_free_pool": f"{prefix}_use_openrouter_free_pool",
    }
    
    # 特殊处理：api_key 的映射
    # 根据前缀决定使用哪个 api_key 变量
    # 应用基础映射：DB 字段有值 且 config.py 中存在对应变量，才写入
    for db_field, config_var in field_mapping.items():
        if db_field in config and config[db_field] is not None:
            if hasattr(cfg_module, config_var):
                value = config[db_field]
                # 布尔字段统一转换
                if db_field == "use_openrouter_free_pool":
                    value = bool(value)
                updates[config_var] = value
    
    # 处理 api_key
    if "api_key" in config and config["api_key"]:
        api_key_var = _API_KEY_MAPPING.get(prefix)
        if api_key_var and hasattr(cfg_module, api_key_var):
            updates[api_key_var] = config["api_key"]
    
    # 特殊字段映射（根据前缀）
    if prefix == "summary_batch":
        # summary_batch 有额外的字段
        if "endpoint" in config and config["endpoint"]:
            updates["summary_batch_endpoint"] = config["endpoint"]
        if "completion_window" in config and config["completion_window"]:
            updates["summary_batch_completion_window"] = config["completion_window"]
        if "out_root" in config and config["out_root"]:
            updates["summary_batch_out_root"] = config["out_root"]
        if "jsonl_root" in config and config["jsonl_root"]:
            updates["summary_batch_jsonl_root"] = config["jsonl_root"]
    
    # 特殊处理：org 前缀的 concurrency 字段名不同
    if prefix == "org" and "concurrency" in config and config["concurrency"] is not None:
        updates["pdf_info_concurrency"] = config["concurrency"]
        # 移除可能错误添加的 org_concurrency
        updates.pop(f"{prefix}_concurrency", None)
    
    return updates


def _validate_llm_usage_prefix(prefix: str) -> str:
    normalized = str(prefix or "").strip()
    if normalized not in LLM_USAGE_PREFIXES:
        raise ValueError(f"不支持的模型应用前缀：{normalized or '(空)'}")
    return normalized


def find_matching_usage_prefixes(
    config: Dict[str, Any],
    *,
    excluded_prefixes: Optional[set[str]] = None,
) -> list[str]:
    """Infer legacy bindings by comparing the complete active connection.

    Older deployments copied model values into config.json without recording
    the source config ID. Exact matching (including the API key) lets the first
    edit migrate those legacy applications into durable bindings safely.
    """
    cfg_module = _get_config_module()
    excluded = excluded_prefixes or set()
    matches: list[str] = []
    for prefix in LLM_USAGE_PREFIXES:
        if prefix in excluded:
            continue
        expected = map_llm_config_to_variables(config, prefix)
        identity_names = {
            f"{prefix}_base_url",
            f"{prefix}_model",
            f"{prefix}_use_openrouter_free_pool",
            _API_KEY_MAPPING.get(prefix, ""),
        }
        identity = {
            name: value
            for name, value in expected.items()
            if name in identity_names and name
        }
        if not identity or not any(name.endswith("_model") for name in identity):
            continue
        if all(getattr(cfg_module, name, None) == value for name, value in identity.items()):
            matches.append(prefix)
    return matches


def reapply_llm_config(
    config_id: int,
    *,
    extra_prefixes: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Reapply a model config to every persisted (and migrated) binding."""
    from services import llm_config_service

    config = llm_config_service.get_config(config_id)
    if not config:
        raise ValueError(f"模型配置 {config_id} 不存在")

    prefixes = set(llm_config_service.get_bound_prefixes(config_id))
    prefixes.update(extra_prefixes or [])
    normalized = sorted({_validate_llm_usage_prefix(item) for item in prefixes})
    if not normalized:
        return {"config": None, "applied_prefixes": []}

    merged_updates: Dict[str, Any] = {}
    for prefix in normalized:
        updates = map_llm_config_to_variables(config, prefix)
        if not updates:
            raise ValueError(f"无法为前缀 '{prefix}' 生成映射")
        merged_updates.update(updates)

    result = config_service.update_config(merged_updates)
    llm_config_service.set_bindings({prefix: config_id for prefix in normalized})
    return {"config": result, "applied_prefixes": normalized}


def update_and_reapply_llm_config(
    config_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Update a library config and synchronize every active application."""
    from services import llm_config_service

    existing = llm_config_service.get_config(config_id)
    if not existing:
        raise ValueError(f"模型配置 {config_id} 不存在")

    binding_map = llm_config_service.get_binding_map()
    legacy_prefixes = find_matching_usage_prefixes(
        existing,
        excluded_prefixes=set(binding_map),
    )
    updated = llm_config_service.update_config(config_id, data)
    if not updated:
        raise ValueError(f"模型配置 {config_id} 不存在")
    sync_result = reapply_llm_config(
        config_id,
        extra_prefixes=legacy_prefixes,
    )
    return {
        "config": updated,
        "applied_prefixes": sync_result["applied_prefixes"],
    }


def map_prompt_config_to_variable(config: Dict[str, Any], variable_name: str) -> Dict[str, Any]:
    """将提示词配置映射到指定的config.py变量。
    
    Args:
        config: 提示词配置字典（来自数据库）
        variable_name: 目标变量名（如 "theme_select_system_prompt", "system_prompt" 等）
        
    Returns:
        映射后的变量字典，可直接用于 config_service.update_config
    """
    if "prompt_content" not in config:
        raise ValueError("配置中缺少 prompt_content 字段")
    
    return {
        variable_name: config["prompt_content"]
    }


def apply_llm_config(config_id: int, usage_prefix: str) -> Dict[str, Any]:
    """应用模型配置到config.py。
    
    Args:
        config_id: 模型配置ID
        usage_prefix: 使用前缀（如 "theme_select", "org", "summary" 等）
        
    Returns:
        更新后的配置字典
    """
    from services import llm_config_service
    
    usage_prefix = _validate_llm_usage_prefix(usage_prefix)

    # 获取配置
    config = llm_config_service.get_config(config_id)
    if not config:
        raise ValueError(f"模型配置 {config_id} 不存在")
    
    # 映射到变量
    updates = map_llm_config_to_variables(config, usage_prefix)
    
    if not updates:
        raise ValueError(f"无法为前缀 '{usage_prefix}' 生成映射")
    
    # 应用更新，并记录来源配置，后续编辑该配置时可自动同步。
    result = config_service.update_config(updates)
    llm_config_service.set_binding(usage_prefix, config_id)
    return result


def apply_prompt_config(config_id: int, variable_name: str) -> Dict[str, Any]:
    """应用提示词配置到config.py。
    
    Args:
        config_id: 提示词配置ID
        variable_name: 目标变量名（如 "theme_select_system_prompt", "system_prompt" 等）
        
    Returns:
        更新后的配置字典
    """
    from services import prompt_config_service
    
    # 获取配置
    config = prompt_config_service.get_config(config_id)
    if not config:
        raise ValueError(f"提示词配置 {config_id} 不存在")
    
    # 映射到变量
    updates = map_prompt_config_to_variable(config, variable_name)
    
    # 应用更新
    return config_service.update_config(updates)


def batch_apply(
    llm_applies: list,
    prompt_applies: list,
) -> Dict[str, Any]:
    """批量应用模型配置和提示词配置到 config.py，仅触发一次文件写入。

    Args:
        llm_applies: 列表，每项为 {"config_id": int, "prefix": str}
        prompt_applies: 列表，每项为 {"config_id": int, "variable": str}

    Returns:
        更新后的完整配置字典
    """
    from services import llm_config_service, prompt_config_service

    merged_updates: Dict[str, Any] = {}
    binding_updates: Dict[str, int] = {}
    errors: list = []

    for item in llm_applies:
        config_id = item.get("config_id")
        try:
            prefix = _validate_llm_usage_prefix(item.get("prefix", ""))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        config = llm_config_service.get_config(config_id)
        if not config:
            errors.append(f"模型配置 {config_id} 不存在")
            continue
        updates = map_llm_config_to_variables(config, prefix)
        if not updates:
            errors.append(f"无法为前缀 '{prefix}' 生成映射")
            continue
        merged_updates.update(updates)
        binding_updates[prefix] = int(config_id)

    for item in prompt_applies:
        config_id = item.get("config_id")
        variable = item.get("variable", "")
        config = prompt_config_service.get_config(config_id)
        if not config:
            errors.append(f"提示词配置 {config_id} 不存在")
            continue
        updates = map_prompt_config_to_variable(config, variable)
        merged_updates.update(updates)

    if errors and not merged_updates:
        raise ValueError("批量应用失败：" + "; ".join(errors))

    if not merged_updates:
        raise ValueError("没有有效的配置需要应用")

    result = config_service.update_config(merged_updates)
    llm_config_service.set_bindings(binding_updates)
    return {
        "config": result,
        "errors": errors,
        "applied_count": len(merged_updates),
        "applied_prefixes": sorted(binding_updates),
    }
