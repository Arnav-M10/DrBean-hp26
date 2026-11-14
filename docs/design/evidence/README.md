# Design review evidence

Before: actual current mainaa51f16 at1440px. After: Owner2's dark design on
the same journey, desktop1440px and phone390px. The baseline image comes from the
actual manual browser/Counterdex walkthrough with explicitly synthetic input;
the candidates and native results were computed and independently replayed.
No real researcher data or credentials are shown. These are review captures,
not expected pixels used to force tests to pass.

- [Before desktop](before-desktop.png)
- [After desktop](after-desktop.png)
- [After phone](after-phone.png)
- [Real checked baseline and plots](checked-baseline.png)
- [Rendered contrast measurements](contrast.json)
- [Presentation checks and observed layout cost](presentation.json)
- [Real launcher/browser scientific acceptance](research-browser.json)

The presentation runner uses explicit offline API failures and labelled hook
fixtures. The separate scientific runner uses the actual launcher/API/worker,
real Counterdex, native downloads and fresh replay. Neither makes model calls.
The exact final head and commands are recorded in PR49 and the design handoff.
