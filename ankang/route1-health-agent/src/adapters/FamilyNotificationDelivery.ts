import type { DeliverFn, DeliveryOutcome } from '../engine/notify';
import { sendBrowserPush } from './BrowserNotificationChannel';
import { loadWebhookConfig, sendWebhookPush } from './WebhookPushChannel';
/** Existing adapters report sent on constructor/HTTP acceptance; neither is a recipient delivery receipt. */
function accepted(outcome: DeliveryOutcome): DeliveryOutcome {
  return outcome.status === 'sent'
    ? { ...outcome, status: 'accepted', detail: '渠道已接受请求；尚无家属送达回执' }
    : outcome;
}
export const browserOnlyDelivery: DeliverFn = (notification) => [
  accepted(sendBrowserPush(`family-${notification.finding.id}`, notification.finding.title, notification.message)),
];
export const browserFamilyDelivery: DeliverFn = async (notification) => {
  const outcomes = await browserOnlyDelivery(notification);
  const config = loadWebhookConfig();
  if (config)
    outcomes.push(
      accepted(await sendWebhookPush(config, { title: notification.finding.title, body: notification.message })),
    );
  return outcomes;
};
