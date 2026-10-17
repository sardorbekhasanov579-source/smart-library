"""Katalog: mualliflar va toifalar (authors, categories jadvallari)."""
from django.db import models


class Author(models.Model):
    """ER: authors (id, full_name, birth_year, description)."""

    full_name = models.CharField("Muallif F.I.Sh.", max_length=200, unique=True)
    birth_year = models.PositiveIntegerField("Tug'ilgan yili", null=True, blank=True)
    description = models.TextField("Izoh", blank=True)

    class Meta:
        db_table = "authors"
        verbose_name = "Muallif"
        verbose_name_plural = "Mualliflar"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    @property
    def books_count(self):
        return self.books.count()


class Category(models.Model):
    """ER: categories (id, name, description, parent_id) - ierarxik toifalar."""

    name = models.CharField("Toifa nomi", max_length=150)
    description = models.TextField("Tavsif", blank=True)
    parent = models.ForeignKey(
        "self",
        verbose_name="Yuqori toifa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    class Meta:
        db_table = "categories"
        verbose_name = "Toifa"
        verbose_name_plural = "Toifalar"
        ordering = ["name"]
        unique_together = [("name", "parent")]

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} / {self.name}"
        return self.name

    @property
    def level(self):
        """Ierarxiyadagi chuqurlik (0 - ildiz)."""
        depth, node = 0, self.parent
        while node is not None and depth < 10:
            depth += 1
            node = node.parent
        return depth

    def all_descendant_ids(self):
        """O'zi va barcha ichki toifalarining id lari."""
        ids = [self.pk]
        for child in self.children.all():
            ids.extend(child.all_descendant_ids())
        return ids
