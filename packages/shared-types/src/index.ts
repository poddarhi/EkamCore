export type {
  components,
  operations,
  paths,
} from "./generated/ekamcore-api";

import type { components as ApiComponents } from "./generated/ekamcore-api";

export type ResponseMeta = ApiComponents["schemas"]["ResponseMeta"];
export type ProblemResponse = ApiComponents["schemas"]["ProblemResponse"];
export type HealthResponse = ApiComponents["schemas"]["HealthResponse"];
export type VersionResponse = ApiComponents["schemas"]["VersionResponse"];
export type TodayCard = ApiComponents["schemas"]["TodayCard"];
export type TodayResponse = ApiComponents["schemas"]["TodayResponse"];
export type RecapResponse = ApiComponents["schemas"]["RecapResponse"];
export type JobStatusResponse = ApiComponents["schemas"]["JobStatusResponse"];
