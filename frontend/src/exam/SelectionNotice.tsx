import { TaskSelection } from '../api'

/** Explain automatic practice selection without suggesting official difficulty calibration. */
export default function SelectionNotice({ selection }: { selection?: TaskSelection | null }) {
  if (!selection) return null
  return <div className="tile font-read text-sm leading-relaxed" aria-label="Why this task was selected">
    <span className="font-pixel font-semibold text-cyan">Why this task? </span>
    <span className="text-mist">{selection.rationale}</span>
  </div>
}
