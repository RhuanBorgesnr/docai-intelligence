"""Create CaseEmbedding model with pgvector VectorField."""

from django.db import migrations, models
import django.db.models.deletion
from pgvector.django import VectorField


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("orchestrator", "0001_initial"),
        ("documents", "0000_pgvector_extension"),  # ensures vector extension exists
    ]

    operations = [
        migrations.CreateModel(
            name="CaseEmbedding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("embedding", VectorField(dimensions=384)),
                ("content_hash", models.CharField(db_index=True, max_length=64)),
                ("indexed_at", models.DateTimeField(auto_now=True)),
                ("case", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="embedding_record",
                    to="orchestrator.case",
                )),
            ],
            options={
                "indexes": [
                    models.Index(fields=["content_hash"], name="search_caseemb_hash_idx"),
                ],
            },
        ),
    ]
