"""Acting on the person's account (LinkedIn, 17/10: the models planned "Seguir" three people nobody asked for)."""
import pytest

from anchor.engine.sensitive import classify, unrequested


@pytest.mark.parametrize("description, element", [
    ("Seguir JAINE DA COSTA NERI", ""), ("Follow Ollama", ""), ("click the button", "Seguir Juliana Asperti"),
    ("Curtir", ""), ("Comentar", ""), ("Compartilhar", ""), ("Like", ""), ("Repost", ""), ("Conectar", "Conectar"),
])
def test_acting_on_the_account_is_its_own_sensitive_category(description, element):
    assert classify("click", description, element) == "account"


@pytest.mark.parametrize("description", ["Seguir", "Seguir para o pagamento", "Follow to the next step", "Próximo"])
def test_going_on_is_not_following_anyone(description):
    assert classify("click", description, "") != "account"


def test_only_a_verb_of_the_family_asks_for_it():
    assert unrequested("account", "entre no site, mostre todas as vagas e salve", "Seguir JAINE", "")
    assert unrequested("account", "abra o perfil da Jaine", "Seguir Jaine", "")          # the same person is not a verb
    assert not unrequested("account", "siga as três primeiras pessoas da lista", "Seguir JAINE", "")
    assert not unrequested("account", "like the latest post and share it", "Like", "")
