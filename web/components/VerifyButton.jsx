import { ECOURTS_URL } from "../lib/constants";
import { ExtIcon } from "./Icons";

// Anchor styled as a button that opens the eCourts portal in a new tab so the
// user can verify the source site really is down.
export default function VerifyButton({ className = "btn" }) {
  return (
    <a className={className} href={ECOURTS_URL} target="_blank" rel="noopener noreferrer">
      Verify <ExtIcon size={14} />
    </a>
  );
}
