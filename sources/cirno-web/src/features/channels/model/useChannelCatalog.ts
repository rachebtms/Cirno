import { useEffect, useMemo, useState } from "react";
import type { TFunction } from "i18next";
import type { CirnoFeaturesPayload } from "@/lib/contracts/channels";
import {
  channelCatalog,
  channelGroups,
  defaultChannelFilter,
  type ChannelFilter,
} from "./catalog";

export function useChannelCatalog(
  owner: unknown,
  payload: CirnoFeaturesPayload | null,
  t: TFunction,
) {
  const channels = useMemo(() => channelCatalog(payload, t), [payload, t]);
  const [state, setState] = useState({
    owner,
    query: "",
    filter: null as ChannelFilter | null,
  });
  const current =
    state.owner === owner ? state : { owner, query: "", filter: null };
  const filter = current.filter ?? defaultChannelFilter(channels);
  useEffect(() => {
    if (payload && (state.owner !== owner || state.filter === null))
      setState((previous) => ({
        owner,
        query: previous.owner === owner ? previous.query : "",
        filter: defaultChannelFilter(channels),
      }));
  }, [owner, payload, channels, state.owner, state.filter]);
  return {
    channels,
    query: current.query,
    filter,
    groups: channelGroups(channels, current.query, filter, t),
    changeQuery: (query: string) => setState({ owner, query, filter }),
    changeFilter: (filter: ChannelFilter) =>
      setState({ owner, query: current.query, filter }),
  };
}
