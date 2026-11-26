import { portalWrite } from '@/lib/portal-proxy';

export async function POST(req: Request) {
  return portalWrite(req, 'device/link_device', true);
}
