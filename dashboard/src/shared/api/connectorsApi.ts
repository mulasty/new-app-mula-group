import { api } from "@/shared/api/client";
import { ConnectorAvailability, ConnectorHealth } from "@/shared/api/types";

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

export async function getConnectorHealth(connectorId: string): Promise<ConnectorHealth> {
  const response = await api.get<ConnectorHealth>(`/connectors/${connectorId}/health`);
  return response.data;
}

export async function refreshConnectorToken(connectorId: string): Promise<{ updated: boolean; status?: string }> {
  const response = await api.post<{ updated: boolean; status?: string }>(`/connectors/${connectorId}/refresh-token`);
  return response.data;
}

export async function disconnectConnector(connectorId: string): Promise<{ updated: boolean; status?: string }> {
  const response = await api.post<{ updated: boolean; status?: string }>(`/connectors/${connectorId}/disconnect`);
  return response.data;
}

export async function testConnectorPublish(
  connectorId: string,
  scenario: string
): Promise<{ updated: boolean; scenario: string; ttl_seconds: number }> {
  const response = await api.post<{ updated: boolean; scenario: string; ttl_seconds: number }>(
    `/connectors/${connectorId}/test-publish`,
    null,
    { params: { scenario } }
  );
  return response.data;
}
