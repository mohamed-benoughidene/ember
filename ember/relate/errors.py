"""Relate engine errors. Codes are stable and never reused."""

from __future__ import annotations

from ember.errors import EmberError


class RelateError(EmberError):
    code = "RELATE-000"
    name = "RelateError"


class ItemIdNotFound(RelateError):
    code = "RELATE-001"
    name = "ItemIdNotFound"


class LinkTypeNotInClosedSet(RelateError):
    code = "RELATE-005"
    name = "LinkTypeNotInClosedSet"


class SourceTargetTypeIncompatible(RelateError):
    code = "RELATE-006"
    name = "SourceTargetTypeIncompatible"


class SupersedesTargetClosed(RelateError):
    code = "RELATE-007"
    name = "SupersedesTargetClosed"


class PremiseRuleViolated(RelateError):
    code = "RELATE-008"
    name = "PremiseRuleViolated"


class DuplicateLink(RelateError):
    code = "RELATE-009"
    name = "DuplicateLink"


class SelfLink(RelateError):
    code = "RELATE-010"
    name = "SelfLink"


class ChangeLogWriteFailed(RelateError):
    code = "RELATE-011"
    name = "ChangeLogWriteFailed"


class DbOpenFailed(RelateError):
    code = "RELATE-012"
    name = "DbOpenFailed"


class DbMigrationFailed(RelateError):
    code = "RELATE-013"
    name = "DbMigrationFailed"


class SchemaOutdated(RelateError):
    code = "RELATE-014"
    name = "SchemaOutdated"


class ItemsReadFailed(RelateError):
    code = "RELATE-016"
    name = "ItemsReadFailed"


class EmbedderLoadFailed(RelateError):
    code = "RELATE-017"
    name = "EmbedderLoadFailed"


class EmbedderEncodeFailed(RelateError):
    code = "RELATE-018"
    name = "EmbedderEncodeFailed"


class EmbeddingWriteFailed(RelateError):
    code = "RELATE-019"
    name = "EmbeddingWriteFailed"


class GraphReadFailed(RelateError):
    code = "RELATE-021"
    name = "GraphReadFailed"


class CosineComputeFailed(RelateError):
    code = "RELATE-022"
    name = "CosineComputeFailed"


class MetadataReadFailed(RelateError):
    code = "RELATE-023"
    name = "MetadataReadFailed"


class TargetNotInCandidates(RelateError):
    code = "RELATE-024"
    name = "TargetNotInCandidates"


class ProposalSourceMismatch(RelateError):
    code = "RELATE-025"
    name = "ProposalSourceMismatch"


class SourceItemNotFound(RelateError):
    code = "RELATE-026"
    name = "SourceItemNotFound"


class TargetItemNotFound(RelateError):
    code = "RELATE-027"
    name = "TargetItemNotFound"


class SupersedesCycle(RelateError):
    code = "RELATE-028"
    name = "SupersedesCycle"


class LinkWriteFailed(RelateError):
    code = "RELATE-029"
    name = "LinkWriteFailed"


class SchemaValidationFailed(RelateError):
    code = "RELATE-030"
    name = "SchemaValidationFailed"


class UserAbort(RelateError):
    code = "RELATE-031"
    name = "UserAbort"


class AiCallFailed(RelateError):
    code = "RELATE-032"
    name = "AiCallFailed"


class AiResponseSchemaInvalid(RelateError):
    code = "RELATE-033"
    name = "AiResponseSchemaInvalid"


class ConfigMissing(RelateError):
    code = "RELATE-035"
    name = "ConfigMissing"


class AiResponseWriteFailed(RelateError):
    code = "RELATE-036"
    name = "AiResponseWriteFailed"
