// A fresh Data entry is a new draft, not permission to reopen an earlier study.
export const savedStudyId = entry => entry?.sessionId || entry?.analysisId || entry?.comparisonId || null

export const requestsSavedStudy = hash => /^#(?:check|result(?:-readings|-files)?|next)$/.test(hash)
