# Phase 3 — Persistent meal-plan review (development build)

## New endpoints
- POST `/api/v1/meal-plans/drafts`: authenticated dietitian saves a screened candidate plan.
- GET `/api/v1/meal-plans/drafts/{plan_id}`: assigned dietitian inspects draft.
- POST `/api/v1/meal-plans/drafts/{plan_id}/decision`: assigned dietitian approves, modifies or rejects once; modification requires complete revised schedule.
- GET `/api/v1/meal-plans/approved/{plan_id}`: authenticated client can access their own approved plan only.

## Development-only setup
Apply `back-end/migrations/007_meal_plan_review.sql` to an isolated DEVELOPMENT database before using these endpoints with DATABASE_ENABLED=true. Do not run migrations on the Oracle Cloud production database. In-memory mode loses drafts on restart. No Docker or integration tests have been performed.

## Limitations
- Approval is a workflow state, not medical validation; nutrition adequacy, allergens, ingredient derivatives and clinical appropriateness require professional assessment.
- A draft is generated from dietitian-supplied context; automatic synchronization with clinical record fields is not implemented.
- No frontend review editor yet.
- Client endpoint fetches one approved plan by ID; listing, expiration, revocation, and revision history are future work.
- The existing recipe creation endpoint is not authenticated and must be secured before deployment.
- The memory-backed authentication tokens are not production ready.
