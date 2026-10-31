# Business context and rules

The product simulates cloud-storage billing. A customer has an authenticated session; operators are Django users with `is_staff`. Plan/payment records are the source of entitlement values. There is no external payment provider. The intended primary outcome is restoring a previously purchased entitlement; the currently wired HTTP outcome is a human-support queue entry.

Paths below are relative to the repository root. Rule IDs remain stable within this bundle. All enforcement evidence is inspected source; runtime results are **Not verified**.

| Rule | Requirement and actual enforcement | Evidence / status |
| --- | --- | --- |
| BR-01 | Identify the customer from the session; scope customer resources by owner. | `backend/config/settings.py:REST_FRAMEWORK`, `backend/apps/support/services.py:owned_conversation`, `get_subscription`, `propose_action`, `_execute`; implemented |
| BR-02 | Require CSRF for browser writes, including anonymous login. Invalid credentials use a generic denial; logout ends the session. | `backend/apps/accounts/views.py:csrf`, `LoginView.post`, `logout`; `csrf_protect` and configured middleware; implemented |
| BR-03 | Accept only declared JSON fields; message text <=4000 characters, client ID <=128; confirmation cannot carry mutable parameters. | `backend/apps/support/serializers.py:StrictSerializer`, `MessageInput`, `EmptyInput`; `backend/apps/accounts/views.py:LoginInput`; implemented |
| BR-04 | Synchronize only the owner's successful, current, unapplied payment; reject superseded purchases and equal/newer existing entitlement. | `backend/apps/support/services.py:eligible_payment`, `propose_action`, `_execute`; implemented internally, no HTTP activation caller |
| BR-05 | Use the payment's exact plan and period end; commit payment application, subscription version and successful action together. A successful action replay performs no new mutation. | `backend/apps/support/services.py:_execute`; implemented internally; current subscription is returned on replay |
| BR-06 | Require a separate validated critic review. Only allow with no missing fields can authorize a candidate. Do not let customer text manufacture a review. | `backend/apps/support/services.py:record_review`; implemented validation; trusted critic caller still absent |
| BR-07 | Cancellation means `auto_renew=False` and leaves `period_end`, plan and subscription status unchanged. Require an authenticated empty-body endpoint confirmation for a stored proposal. | `backend/apps/support/views.py:confirm`, `backend/apps/support/services.py:confirm_cancellation`, `_execute`; implemented endpoint, proposal integration partial |
| BR-08 | Proposals expire after ten minutes and bind subscription version; changed state or expired approval returns a conflict. | `backend/apps/support/services.py:propose_action`, `_execute`; implemented checks, no automatic expired-status transition |
| BR-09 | Serialize each conversation's AI turn with a server UUID token/version and 45-second lease; reject stale writes/replies and recover an expired lease on the next message. | `backend/apps/support/services.py:begin_turn`, `check_turn`, `finish_turn`; implemented |
| BR-10 | Preserve the transcript on handoff, clear the lease, reject pending proposals and pause AI. | `backend/apps/support/services.py:handoff_to_operator`; implemented deterministic summary; HTTP sends every AI-mode request here |
| BR-11 | Require staff for queue/claim; only assigned staff can reply/resolve. Claim is transactional and repeated claim by the same operator is harmless. | `backend/apps/support/views.py:operator_queue`, `operator_detail`, `claim`, `assigned_conversation`, `operator_messages`, `resolve`; implemented |
| BR-12 | Deduplicate messages by conversation/sender/client ID; reject ID reuse with different text. | `backend/apps/support/models.py:Message.Meta`; `backend/apps/support/services.py:begin_turn`; `backend/apps/support/views.py:operator_messages`; implemented |
| BR-13 | Seed local synthetic accounts only with DEBUG and a locally supplied password >=12 characters; preserve existing state. | `backend/apps/support/management/commands/seed_demo.py:Command.handle`; implemented; existing usernames are reused without privilege repair |
| BR-14 | Refunds require human review; never claim an actual bank refund. | No refund execution code; `backend/apps/support/views.py:messages` transfers all new AI-mode messages to staff; refund-specific intent recognition is planned |

## Demo policy, not commercial or legal guarantees

`Command.handle` creates Free (5 GB, 0 UAH), Plus (100 GB, 99 UAH) and Pro (1000 GB, 199 UAH) if absent. The seeded paid period is from one day before seed time to 29 days after it. These are invented demonstration values, not a refund promise or a recurring billing implementation. Existing plan records are not overwritten.

## Requirements that remain incomplete

The actor, critic, typed model tools, four policy prompt files, configured provider deadline/turn budget and live Gemma check are planned. No code checks that a passed review originated from a real critic: that is the future trusted orchestrator's responsibility. There is no automatic renewal job, actual refund, payment ingestion API, refund eligibility engine or new-customer subscription provisioning. Product screens and measured outcomes are absent.

Open policy question: synchronization currently preserves `auto_renew`; the seeded unpaid-entitlement scenario therefore keeps renewal disabled after synchronization. Any different renewal policy needs an agreed domain change, not a documentation assumption.
