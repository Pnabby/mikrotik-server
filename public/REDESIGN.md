The customer redesign follows the supplied reference with Sora headings, DM Sans body
text, navy signal-ring heroes, blue controls, white cards, and a shared customer header
and footer. Colors and type sizes are centralized in `src/styles/tokens.css`.

Category tiles still open their existing plan URLs. Every plan in the selected category
appears together, without plan pagination. Promotions remain above the category tiles.
Customer labels use categories instead of "plan groups". The price announcement and
its dialog were removed; the floating help icon and support panel remain available.

The changes cover Overview, Plans, category plan lists, purchase confirmation and
payment states, Purchases, Profile and its dialogs, Raise an issue and issue history,
login, signup, recovery, phone verification, Terms, Privacy, loading states, and errors.
The externally hosted Paystack checkout keeps Paystack's interface. Payment APIs,
registration/authentication, issue handling, transfer/deletion behavior, and routes
were preserved apart from removing the requested plan pagination.

This redesign changes only `public/`. Admin, backend, and root README contents were
verified against their state at the start of this request; the earlier notification
badge fix remains in place.

Changed and added files:

- `public/REDESIGN.md`
- `public/index.html`
- `public/src/App.jsx`
- `public/src/main.jsx`
- `public/src/components/AccountHeader.jsx`
- `public/src/components/PageLoadingState.jsx`
- `public/src/components/PageHero.jsx`
- `public/src/components/PlanCategoryCard.jsx`
- `public/src/components/SiteFooter.jsx`
- `public/src/components/StatusPill.jsx`
- `public/src/pages/AccountPage.jsx`
- `public/src/pages/ForgotPinPage.jsx`
- `public/src/pages/IssuesPage.jsx`
- `public/src/pages/LegalPage.jsx`
- `public/src/pages/LoginPage.jsx`
- `public/src/pages/ProfilePage.jsx`
- `public/src/pages/SignupPage.jsx`
- `public/src/pages/VerifyPhonePage.jsx`
- `public/src/styles/account.css`
- `public/src/styles/issues.css`
- `public/src/styles/signup.css`
- `public/src/styles/support.css`
- `public/src/styles/site.css`
- `public/src/styles/tokens.css`

Removed files:

- `public/src/components/PriceNotice.jsx`
- `public/src/components/price-notice.css`

Validation: public lint and production build pass, as do all seven existing public
tests. Browser checks used mocked APIs and verified customer pages at 1440px, 768px,
400px, and 320px, all plans on one page, promotions, purchase/claim request payloads,
issue submission, profile dialogs, support, shared layout, no horizontal page overflow,
and error/empty/loading/reduced-motion states. Short-phone checks cover a 400×675
viewport, visible keyboard focus, round floating help, and scrollable purchase dialogs.
All customer stylesheet tokens resolve; primary text, links, brand controls, and the
status palette meet 4.5:1 contrast against white.
