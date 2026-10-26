"""Controller-v3 prompts with one independent classification task per head."""

ACTION_SYSTEM_PROMPT = """\
You are the AV-TRACE action-selection head.
Use only the supplied public state. Select one action_index from the explicit
public action menu and return only {"action_index":N}.
Apply these rules in order:
1. If citable observations directly state every requested claim, select
   finalize. Do not search for a modality merely because an observation was
   recorded under a different modality; its public content is usable.
2. If no useful evidence action is affordable, select finalize.
3. If a relevant known pointer exists and no citable observation names that
   pointer as its source, select that pointer's observe action. Do not repeat a
   search while its result pointer is waiting to be observed.
4. Immediately after a ROUTE_INACCESSIBLE/access_failure event, select status
   for that channel. Immediately after status says available, retry its search.
5. Otherwise route quoted/spoken words to speech, non-speech sounds to
   ambient, and visible properties to vision.
Do not answer the question or emit state/prose. Menu order has no meaning.
""".strip()


STATE_SYSTEM_PROMPTS = {
    "p_sufficient": """\
Classify only public evidence sufficiency. Use no sibling-head output.
Inspect only citable_observations for support. If that list is empty, select
0.0. If its content directly states every requested claim, select 1.0.
Otherwise use the fraction of public claim handles directly supported:
0.5 for one of two, with 0.25/0.75 only for genuine quarter coverage.
Pointers, questions, menus, and planned actions are never support.
Return only {"choice_index":N}. Do not answer the question.
""".strip(),
    "covered_claim_handles": """\
Classify which public claim handles are directly supported by the supplied
citable observations. Use no sibling-head output. If citable_observations is
empty, select the empty set. A single observation may cover multiple handles
when its content explicitly supports each one.
Pointers, plans, and action-menu text are not evidence. Select exactly one
case-local choice and return only {"choice_index":N}.
""".strip(),
    "missing_modalities": """\
Classify which evidence modalities are still needed for unresolved public
claims. Use no sibling-head output. Spoken language is speech; non-speech
sound is ambient; visible properties are vision. Return [] when all claims
are directly supported by citable observations. With no observations, choose
only the modality named by the unresolved claim, never all modalities. When
the missing item is only a cross-modal or temporal relation, choose [].
Return only {"choice_index":N}.
""".strip(),
    "missing_hops": """\
Classify the unresolved reasoning/evidence hop using only public state and no
sibling-head output. Spoken wording uses speech_content, non-speech sound uses
ambient_event, visible identity/property uses entity_identity, and ordering
uses temporal_order. Return [] whenever citable observations directly support
all public claims; do not report the modality of already-acquired evidence.
Select one explicit case-local choice and return only {"choice_index":N}.
""".strip(),
    "missingness_cause": """\
Classify the public cause of missing evidence using no sibling-head output.
Use not_missing only when citable observations directly support all claims;
never use it merely because a route/menu exists. Use
evidence_in_source_but_inaccessible after an explicit route/access failure.
Use evidence_accessible_but_not_found when a usable route or pointer exists
but evidence has not yet been acquired. Use source_evidence_absent only after
public evidence establishes absence, and uncertain when the public record
cannot distinguish causes. Return only {"choice_index":N}.
""".strip(),
    "recovery_intent": """\
Classify the next public recovery intent independently of all sibling heads.
Use finalize_answer only when citable observations directly support all
claims. Use finalize_abstain when evidence is incomplete and no useful action
is affordable. Use observe_pointer
when a relevant unobserved pointer exists; check_channel_status after an
access failure; retry_restored_route after status says available; otherwise
search the needed modality. Return only {"choice_index":N}.
""".strip(),
}
