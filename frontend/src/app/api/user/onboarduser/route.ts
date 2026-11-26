import { portalWrite } from '@/lib/portal-proxy';

export async function POST(req: Request) {
  return portalWrite(req, 'user/onboard_user');
}
