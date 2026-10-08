import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy · Civic Memory",
  description: "What Civic Memory collects, why, and who else sees it.",
};

// Keep this page in step with the code. If the site or bot starts collecting
// something new, it goes here first.
export default function Privacy() {
  return (
    <main className="wrap prose">
      <header className="mast">
        <div className="eyebrow">
          <Link href="/">Civic Memory</Link>
        </div>
        <h1>Privacy</h1>
        <p>Last updated October 8, 2026.</p>
      </header>

      <p>
        Civic Memory has no accounts, no ads, no analytics, no tracking pixels, and no
        cookies. Here is everything it does keep.
      </p>

      <h2>On this website</h2>
      <ul>
        <li>
          <strong>What you search for.</strong> Each search is written to the server log so we
          can see what people look for and fix searches that come up empty. The log line has
          the search words and nothing else of yours — no name, no cookie, no account.
        </li>
        <li>
          <strong>Our host.</strong> The site runs on{" "}
          <a href="https://fly.io/legal/privacy-policy">Fly.io</a>, which handles standard
          request data such as IP addresses to deliver the page.
        </li>
        <li>
          <strong>&ldquo;Email council about this&rdquo; links</strong> open your own email app. Nothing is
          sent through Civic Memory.
        </li>
      </ul>

      <h2>In the Discord bot</h2>
      <ul>
        <li>
          <strong>/ask.</strong> Your question and the matching records are sent to{" "}
          <a href="https://www.anthropic.com/legal/privacy">Anthropic</a>, whose AI model
          writes the answer. The bot keeps the conversation briefly so it can reply; it is not
          used for anything else.
        </li>
        <li>
          <strong>/watch.</strong> To post alerts, the bot stores the words you watch for, the
          Discord server and channel to post in, and the Discord user ID of whoever set it up.
          <code>/unwatch</code> turns an alert off.
        </li>
        <li>
          Discord itself handles everything else about your account under{" "}
          <a href="https://discord.com/privacy">its own policy</a>.
        </li>
      </ul>

      <h2>What we don&rsquo;t do</h2>
      <p>
        We don&rsquo;t sell or share what we keep, build profiles, or use it for advertising.
        Civic Memory isn&rsquo;t directed at children under 13.
      </p>

      <h2>Questions or removal</h2>
      <p>
        To ask a question or have something removed, open an issue on{" "}
        <a href="https://github.com/mallycarter47-arn/council-record/issues">GitHub</a>.
      </p>

      <p className="foot-note">
        <Link href="/">Back to search</Link>
      </p>
    </main>
  );
}
