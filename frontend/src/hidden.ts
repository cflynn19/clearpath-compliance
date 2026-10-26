// Invisible characters the injection check flags (zero-width, bidi controls, Unicode
// "tag" characters). Mirrors HIDDEN in backend/app/rules/builtin.py.
export const HIDDEN = /[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]|\udb40[\udc00-\udc7f]/g

export function countHidden(text: string): number {
  return [...text.matchAll(HIDDEN)].length
}

export function stripHidden(text: string): string {
  return text.replace(HIDDEN, '')
}
