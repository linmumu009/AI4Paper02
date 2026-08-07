export interface RouteLoadingLocation {
  name?: string | symbol | null
  path: string
}

/**
 * Query/hash updates on the current page are workspace state changes, not page
 * loads. Showing the global loading overlay for them makes card navigation
 * flash even though Vue keeps the same view mounted.
 */
export function shouldShowRouteLoading(
  to: RouteLoadingLocation,
  from: RouteLoadingLocation,
): boolean {
  const staysOnCurrentPage = from.name != null
    && to.name === from.name
    && to.path === from.path

  return !staysOnCurrentPage
}
