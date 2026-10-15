import logging

import stripe
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.payment_services import handle_stripe_event

logger = logging.getLogger(__name__)


class StripeWebhookView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = ()

    def post(self, request):
        if not settings.STRIPE_WEBHOOK_SECRET:
            return Response(
                {"detail": "Stripe webhooks are not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        signature = request.headers.get("Stripe-Signature", "")
        try:
            event = stripe.Webhook.construct_event(
                request.body,
                signature,
                settings.STRIPE_WEBHOOK_SECRET,
            )
        except (ValueError, stripe.SignatureVerificationError):
            return Response(
                {"detail": "Invalid Stripe webhook signature or payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        handle_stripe_event(event)
        logger.info("Processed Stripe webhook event %s", event["id"])
        return Response({"received": True})
