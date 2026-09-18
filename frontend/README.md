# frontend

Responsive **React + TypeScript + Vite** single-page app for FoC. It supports
the requester and courier workflows across desktop and mobile screen sizes
(project M1) and talks only to the **API Gateway**.

## Pages (route stubs)

| Route | Purpose |
| ----- | ------- |
| `/browse` | Courier: browse open errands (Order F2) |
| `/my-requests` | Requester: my posted errands + statuses (Order F1.2) |
| `/new-request` | Create an errand (Order F1.1) |
| `/deliveries` | Courier: accepted orders, pickup/deliver (Order F3) |
| `/profile` | Profile, role toggle, credit balance (User F3) |
| `/admin` | N2H: admin dashboard (project N1) |

## Config

`VITE_API_BASE_URL` (see root `.env.example`) points the app at the gateway.
The tiny client lives in `src/lib/api.ts`.

## Run

```bash
# via the whole stack
make up            # served at http://localhost:5173

# or locally
cd frontend && npm install && npm run dev
```

> Status: **scaffold**. Pages are placeholders; no real API calls yet.
