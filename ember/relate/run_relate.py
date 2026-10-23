"""Engine-core entry point for Relate Phases 3 + 4.

Ties the AI proposal, the raw-response save, the pure gatekeeper and the user
confirm loop together. Every effect goes through a port; this module imports no
storage driver and no provider SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ember.relate.ai_response_store import AiResponseStorePort
from ember.relate.confirm_write import (
    ConfirmPort,
    ConfirmResult,
    LinkStorePort,
    confirm_links,
)
from ember.relate.errors import (
    AiResponseWriteFailed,
    RelateError,
    SchemaValidationFailed,
)
from ember.relate.link_gatekeeper import (
    LinkDraft,
    RejectedLink,
    ValidatedLink,
    validate_add_link,
)
from ember.relate.link_lookup import LinkLookupPort
from ember.relate.link_proposal import (
    LinkProposal,
    LinkProposerPort,
    propose_links_with_retry,
    validate_proposals,
)
from ember.relate.rows import NewItem, RankedCandidate


@dataclass(frozen=True)
class RelatePorts:
    """The four ports Phases 3 + 4 use, plus the user I/O boundary."""

    link_lookup: LinkLookupPort
    link_store: LinkStorePort
    link_proposer: LinkProposerPort
    ai_response_store: AiResponseStorePort
    confirm: ConfirmPort


@dataclass(frozen=True)
class RelateRequest:
    """The data for one relate run. `ranked` is `Pool.ranked` from Phase 2.

    `env` is carried for parity with the CLI wiring; Phase 3 + 4 read no
    environment value directly because the proposer is injected as a port.
    """

    new_item: NewItem
    ranked: list[RankedCandidate]
    env: Mapping[str, str]


def run_relate(ports: RelatePorts, request: RelateRequest) -> ConfirmResult:
    """Run Phase 3, Phase 3.5, the gatekeeper and the Phase 4 confirm loop.

    Raises `RELATE-024` / `RELATE-025` on a bad AI target/source, `RELATE-030`
    when the raw-response owner pair is invalid, `RELATE-036` when the raw
    response cannot be stored, `RELATE-032` after a failed retry, and
    `RELATE-033` on an unparseable first answer. Gatekeeper rule failures are
    counted as `rejected`, not raised.
    """
    candidates = [candidate.item for candidate in request.ranked]
    response = propose_links_with_retry(
        ports.link_proposer, new_item=request.new_item, candidates=candidates
    )
    validate_proposals(
        response.proposals, candidates=candidates, new_item=request.new_item
    )
    _save_raw_response(ports.ai_response_store, request.new_item, response.raw_response)
    validated, gatekeeper_rejected = _gatekeep(
        response.proposals, request.new_item, ports.link_lookup
    )
    result = confirm_links(validated, store=ports.link_store, confirm=ports.confirm)
    return ConfirmResult(
        accepted=result.accepted,
        rejected=result.rejected + gatekeeper_rejected,
        skipped=result.skipped,
        aborted=result.aborted,
    )


def _save_raw_response(
    store: AiResponseStorePort, new_item: NewItem, raw_response: str
) -> None:
    """Phase 3.5: store the raw answer verbatim, mapping failures to codes.

    `ValueError` (both/neither owner set) -> `RELATE-030`. Any other failure,
    including the adapter's own write-error class (e.g. CAPTURE-013
    `ItemDbWriteError`), -> `RELATE-036`. A `RelateError` bug is re-raised
    unchanged so a code fault is never masked as a storage failure.
    """
    try:
        store.save(item_id=new_item.id, raw_response=raw_response)
    except ValueError as exc:
        raise SchemaValidationFailed(
            "ai response owner invalid", item_id=new_item.id
        ) from exc
    except RelateError:
        raise
    except Exception as exc:  # noqa: BLE001 - boundary: any storage failure maps to 036
        raise AiResponseWriteFailed(
            "ai response save failed", item_id=new_item.id
        ) from exc


def _gatekeep(
    proposals: list[LinkProposal],
    new_item: NewItem,
    lookup: LinkLookupPort,
) -> tuple[list[ValidatedLink], int]:
    """Run the pure gatekeeper per proposal; count the rejects."""
    validated: list[ValidatedLink] = []
    rejected = 0
    for proposal in proposals:
        outcome = validate_add_link(
            LinkDraft(
                source_item_id=new_item.id,
                target_item_id=proposal.target_item_id,
                link_type=proposal.link_type,
                rationale=proposal.rationale,
            ),
            lookup,
        )
        if isinstance(outcome, RejectedLink):
            rejected += 1
        else:
            validated.append(outcome)
    return validated, rejected
