from __future__ import annotations


class IntegrityViolationError(RuntimeError):
    def __init__(self, component_id: str, expected_hash: str, proposed_hash: str) -> None:
        self.component_id = component_id
        self.expected_hash = expected_hash
        self.proposed_hash = proposed_hash
        super().__init__(f"integrity_violation:{component_id}")
