import { api } from "@/shared/api/client";
import { ConnectorAvailability } from "@/shared/api/types";

type ConnectorsEnvelope = {
  items: ConnectorAvailability[];
};

export async function listAvailableConnectors(): Promise<ConnectorAvailability[]> {
  const response = await api.get<ConnectorsEnvelope>("/connectors/available");
  return response.data.items ?? [];
}

export async function getConnectorOauthStartUrl(
  platform: string,
  projectId?: string
): Promise<string> {
  const normalized = platform.trim().toLowerCase();
  let path: string;
  switch (normalized) {
    case "linkedin":
      path = "/channels/linkedin/oauth/start";
      break;
    case "facebook":
    case "instagram":
      path = "/channels/meta/oauth/start";
      break;
    default:
      path = `/channels/${normalized}/oauth/start`;
      break;
  }

  const response = await api.get<{ authorization_url: string }>(path, {
    params: {
      ...(projectId ? { project_id: projectId } : {}),
      redirect: false,
    },
  });
  return response.data.authorization_url;
}
