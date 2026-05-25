import apiClient from "./client";

export async function globalSearch(query, limitPerModule = 4) {
  const response = await apiClient.get("/search/global", {
    params: {
      q: query,
      limit_per_module: limitPerModule,
    },
  });
  return response.data;
}
