#!/usr/bin/env python3
"""
Verification script for Feature #7: AgentSpec Pydantic Request/Response Schemas

This script verifies all the feature steps are implemented correctly.
Run with: python tests/verify_feature_7.py
"""

import sys
sys.path.insert(0, "/home/rudih/workspace/AutoBuildr")

def main():
    print("=" * 60)
    print("Feature #7: AgentSpec Pydantic Request/Response Schemas")
    print("=" * 60)
    print()

    # Import schemas
    print("Step 1: Import schemas...")
    try:
        from server.schemas import (
            AgentSpecCreate,
            AgentSpecUpdate,
            AgentSpecResponse,
            ToolPolicy,
            TASK_TYPES,
        )
        print("  ✅ All schemas imported successfully")
    except ImportError as e:
        print(f"  ❌ Import failed: {e}")
        return 1

    # Step 1: Verify AgentSpecCreate required fields
    print()
    print("Step 2: Verify AgentSpecCreate required fields...")
    required_fields = ["name", "display_name", "objective", "task_type", "tool_policy"]
    create_fields = list(AgentSpecCreate.model_fields.keys())
    for field in required_fields:
        if field in create_fields:
            info = AgentSpecCreate.model_fields[field]
            is_required = info.is_required()
            status = "✅" if is_required else "⚠️ (has default)"
            print(f"  {status} {field} - required={is_required}")
        else:
            print(f"  ❌ {field} - MISSING")
            return 1

    # Step 2: Verify optional fields
    print()
    print("Step 3: Verify AgentSpecCreate optional fields...")
    optional_fields = ["icon", "context", "max_turns", "timeout_seconds",
                       "parent_spec_id", "source_feature_id", "priority", "tags"]
    for field in optional_fields:
        if field in create_fields:
            info = AgentSpecCreate.model_fields[field]
            is_required = info.is_required()
            status = "✅" if not is_required else "⚠️ (should be optional)"
            print(f"  {status} {field} - required={is_required}")
        else:
            print(f"  ❌ {field} - MISSING")
            return 1

    # Step 3: Verify task_type validation
    print()
    print("Step 4: Verify task_type allowed values...")
    expected_types = {"coding", "testing", "refactoring", "documentation", "audit", "custom"}
    # TASK_TYPES is a Literal type
    from typing import get_args
    actual_types = set(get_args(TASK_TYPES))
    if actual_types == expected_types:
        print(f"  ✅ task_type values: {sorted(actual_types)}")
    else:
        print(f"  ❌ task_type mismatch. Expected: {expected_types}, Got: {actual_types}")
        return 1

    # Step 4: Verify max_turns range
    print()
    print("Step 5: Verify max_turns range 1-500...")
    max_turns_info = AgentSpecCreate.model_fields["max_turns"]
    metadata = max_turns_info.metadata
    ge_val = None
    le_val = None
    for m in metadata:
        if hasattr(m, "ge"):
            ge_val = m.ge
        if hasattr(m, "le"):
            le_val = m.le
    if ge_val == 1 and le_val == 500:
        print(f"  ✅ max_turns range: {ge_val}-{le_val}")
    else:
        print(f"  ❌ max_turns range incorrect. Expected: 1-500, Got: {ge_val}-{le_val}")
        return 1

    # Step 5: Verify timeout_seconds range
    print()
    print("Step 6: Verify timeout_seconds range 60-7200...")
    timeout_info = AgentSpecCreate.model_fields["timeout_seconds"]
    metadata = timeout_info.metadata
    ge_val = None
    le_val = None
    for m in metadata:
        if hasattr(m, "ge"):
            ge_val = m.ge
        if hasattr(m, "le"):
            le_val = m.le
    if ge_val == 60 and le_val == 7200:
        print(f"  ✅ timeout_seconds range: {ge_val}-{le_val}")
    else:
        print(f"  ❌ timeout_seconds range incorrect. Expected: 60-7200, Got: {ge_val}-{le_val}")
        return 1

    # Step 6: Verify ToolPolicy structure
    print()
    print("Step 7: Verify ToolPolicy structure...")
    tp_fields = list(ToolPolicy.model_fields.keys())
    if "policy_version" in tp_fields and "allowed_tools" in tp_fields:
        pv_info = ToolPolicy.model_fields["policy_version"]
        at_info = ToolPolicy.model_fields["allowed_tools"]
        print(f"  ✅ policy_version default: {pv_info.default}")
        print(f"  ✅ allowed_tools is required: {at_info.is_required()}")
    else:
        print(f"  ❌ ToolPolicy missing required fields")
        return 1

    # Step 7: Verify AgentSpecUpdate has all fields optional
    print()
    print("Step 8: Verify AgentSpecUpdate all fields optional...")
    update_fields = list(AgentSpecUpdate.model_fields.keys())
    all_optional = True
    for field in update_fields:
        info = AgentSpecUpdate.model_fields[field]
        if info.is_required():
            print(f"  ❌ {field} should be optional but is required")
            all_optional = False
    if all_optional:
        print(f"  ✅ All {len(update_fields)} fields are optional")
    else:
        return 1

    # Step 8: Verify AgentSpecResponse matches database model
    print()
    print("Step 9: Verify AgentSpecResponse fields...")
    response_fields = list(AgentSpecResponse.model_fields.keys())
    expected_response = ["id", "name", "display_name", "icon", "spec_version",
                         "objective", "task_type", "context", "tool_policy",
                         "max_turns", "timeout_seconds", "parent_spec_id",
                         "source_feature_id", "created_at", "priority", "tags"]
    missing = set(expected_response) - set(response_fields)
    extra = set(response_fields) - set(expected_response)
    if not missing:
        print(f"  ✅ All expected fields present")
    else:
        print(f"  ❌ Missing fields: {missing}")
        return 1
    if extra:
        print(f"  ℹ️ Additional fields: {extra}")

    # Step 9: Verify docstrings with JSON schema examples
    print()
    print("Step 10: Verify JSON schema examples...")
    if hasattr(AgentSpecCreate, "model_config"):
        config = AgentSpecCreate.model_config
        if "json_schema_extra" in config and "example" in config["json_schema_extra"]:
            print(f"  ✅ AgentSpecCreate has JSON schema example")
        else:
            print(f"  ❌ AgentSpecCreate missing JSON schema example")
            return 1
    else:
        # Check Config class
        if hasattr(AgentSpecCreate.Config, "json_schema_extra"):
            print(f"  ✅ AgentSpecCreate has JSON schema example")
        else:
            print(f"  ❌ AgentSpecCreate missing JSON schema example")
            return 1

    if hasattr(AgentSpecUpdate, "model_config"):
        config = AgentSpecUpdate.model_config
        if "json_schema_extra" in config and "example" in config["json_schema_extra"]:
            print(f"  ✅ AgentSpecUpdate has JSON schema example")
        else:
            print(f"  ❌ AgentSpecUpdate missing JSON schema example")
            return 1
    else:
        if hasattr(AgentSpecUpdate.Config, "json_schema_extra"):
            print(f"  ✅ AgentSpecUpdate has JSON schema example")
        else:
            print(f"  ❌ AgentSpecUpdate missing JSON schema example")
            return 1

    print()
    print("=" * 60)
    print("🎉 All feature steps verified successfully!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
