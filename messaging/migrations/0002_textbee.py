from django.db import migrations, models

import messaging.validators


class Migration(migrations.Migration):
    dependencies = [("messaging", "0001_initial")]

    operations = [
        migrations.RenameField("smsmessage", "provider_sid", "provider_reference"),
        migrations.AddField(
            model_name="smsmessage",
            name="provider",
            field=models.CharField(
                choices=[("textbee", "textbee.dev"), ("twilio", "Twilio")],
                default="twilio",
                max_length=12,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="smsmessage",
            name="provider",
            field=models.CharField(
                choices=[("textbee", "textbee.dev"), ("twilio", "Twilio")],
                default="textbee",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="smsmessage",
            name="provider_device_id",
            field=models.CharField(blank=True, max_length=24),
        ),
        migrations.AlterField(
            model_name="smsmessage",
            name="body",
            field=models.TextField(max_length=9000, validators=[messaging.validators.validate_sms_length]),
        ),
        migrations.AlterField(
            model_name="smsmessage",
            name="error_code",
            field=models.CharField(blank=True, max_length=40),
        ),
    ]
