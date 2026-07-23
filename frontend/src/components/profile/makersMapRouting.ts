export function shouldPlanMakersRoute(showRoute: boolean, placesCount: number): boolean {
  return showRoute && placesCount >= 2;
}
