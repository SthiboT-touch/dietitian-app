# Phase 3 Review UI

Adds an authenticated dietitian review queue endpoint and frontend for creating and reviewing meal plan drafts.

## Limitations
- Not Docker-tested or clinically validated.
- The legacy meal-plan listing and client screen remain separate; clients need a listing endpoint for approved new plans.
- Recipes must have ingredient lists; no nutritional adequacy calculations are performed.
- Modified schedules are entered as JSON and require manual clinical inspection.
- Apply migration 007 only to a backed-up development database. Never apply it to production without explicit authorization.
