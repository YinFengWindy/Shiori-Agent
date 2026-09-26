import { useEffect, useState } from "react";
import type { RoleSemanticDetail, RoleSemanticList, RoleSemanticQuery } from "./roleSemanticMemory";

type LoadedList = { key: string; value: RoleSemanticList | null; error: string; loading: boolean };
type LoadedDetail = { key: string; value: RoleSemanticDetail | null; error: string; loading: boolean };

/** Discards stale plugin responses after role, filter, item, or refresh changes. */
export function useRoleSemanticMemory(
  roleId: string,
  bridgeReady: boolean,
  query: RoleSemanticQuery,
  selectedId: string,
  readList: (roleId: string, query: RoleSemanticQuery) => Promise<RoleSemanticList>,
  readDetail: (roleId: string, itemId: string) => Promise<RoleSemanticDetail>,
) {
  const [revision, setRevision] = useState(0);
  const [loadedList, setLoadedList] = useState<LoadedList | null>(null);
  const [loadedDetail, setLoadedDetail] = useState<LoadedDetail | null>(null);
  const queryKey = JSON.stringify(query);
  const listKey = `${roleId}:${queryKey}:${revision}`;
  const detailKey = `${roleId}:${selectedId}:${revision}`;

  useEffect(() => {
    if (!roleId || !bridgeReady) return;
    let cancelled = false;
    setLoadedList({ key: listKey, value: null, error: "", loading: true });
    void readList(roleId, query).then((value) => {
      if (!cancelled) setLoadedList(value.role_id === roleId
        ? { key: listKey, value, error: "", loading: false }
        : { key: listKey, value: null, error: "角色不匹配", loading: false });
    }).catch((error: unknown) => {
      if (!cancelled) setLoadedList({ key: listKey, value: null, error: error instanceof Error ? error.message : String(error), loading: false });
    });
    return () => { cancelled = true; };
  }, [roleId, bridgeReady, query, revision, readList, listKey]);

  useEffect(() => {
    if (!roleId || !selectedId || !bridgeReady) return;
    let cancelled = false;
    setLoadedDetail({ key: detailKey, value: null, error: "", loading: true });
    void readDetail(roleId, selectedId).then((value) => {
      if (!cancelled) setLoadedDetail(value.role_id === roleId && value.item?.id === selectedId
        ? { key: detailKey, value, error: "", loading: false }
        : { key: detailKey, value: null, error: "记忆条目不匹配", loading: false });
    }).catch((error: unknown) => {
      if (!cancelled) setLoadedDetail({ key: detailKey, value: null, error: error instanceof Error ? error.message : String(error), loading: false });
    });
    return () => { cancelled = true; };
  }, [roleId, bridgeReady, selectedId, revision, readDetail, detailKey]);

  const currentList = loadedList?.key === listKey ? loadedList : null;
  const currentDetail = selectedId && loadedDetail?.key === detailKey ? loadedDetail : null;
  return {
    list: currentList?.value ?? null,
    listLoading: Boolean(roleId && bridgeReady && (!currentList || currentList.loading)),
    listError: currentList?.error ?? "",
    detail: currentDetail?.value?.item ?? null,
    detailLoading: Boolean(selectedId && roleId && bridgeReady && (!currentDetail || currentDetail.loading)),
    detailError: currentDetail?.error ?? "",
    refresh: () => setRevision((value) => value + 1),
  };
}
