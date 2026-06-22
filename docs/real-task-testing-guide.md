# Краткая инструкция для тестирования на реальных задачах

Этот документ для коллег, которые хотят попробовать `gigalphex` на рабочих
задачах и быстро понять, какой сценарий считается нормальным.

## Что делает проект

`gigalphex` - это небольшой Python-раннер поверх GigaCode CLI. Он не заменяет
GigaCode, а задает ему рабочий цикл:

1. Создать или прочитать markdown-план.
2. Найти первый незавершенный раздел `### Task N:`, `### Iteration N:`,
   `### Задача N:` или `### Итерация N:`.
3. Запустить GigaCode на выполнение ровно одного такого раздела.
4. Попросить GigaCode изменить код, обновить тесты, выполнить проверки,
   отметить готовые чекбоксы `[x]` и сделать git-коммит.
5. Повторять, пока задачи не закончатся.
6. После полного выполнения запустить ревью: пять специализированных
   review-агентов, затем synthesis/fix-проход.

Главный артефакт работы - plan-файл с чекбоксами. Главный след исполнения -
progress log в `.gigalphex/progress/`.

## Перед первым запуском

Нужно, чтобы `gigacode` был установлен, залогинен и доступен в `PATH`:

```bash
command -v gigacode
gigacode --version
```

Из корня этого репозитория можно проверить сам `gigalphex`:

```bash
PYTHONPATH=python python3 -m unittest discover -s tests
PYTHONPATH=python python3 -m gigalphex.cli --init
```

Глобальные конфиг и шаблоны промптов автоматически создаются в
`~/.config/gigalphex/`. Если эта директория недоступна для записи, CLI создаёт
`.gigalphex/config` и `.gigalphex/prompts/` в текущем проекте. Если для
конкретного проекта нужны свои версии промптов, создайте локальные
переопределения:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --init-prompts
```

Если тестируете `gigalphex` на другом проекте без установки пакета, запускайте
его из корня целевого проекта с абсолютным `PYTHONPATH`:

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli --init
```

## Рекомендуемый сценарий: план -> проверка -> выполнение

Один раз установите встроенный skill планирования:

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli --install-planning-skill
```

По умолчанию он устанавливается в
`~/.gigacode/skills/planning/SKILL.md`. Если ваша версия GigaCode использует
другой каталог, передайте `--skill-dir PATH`.

1. Сформулируйте задачу как обычный рабочий запрос:

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli --plan "добавить health check endpoint"
```

В обычном терминале команда запускает установленный в GigaCode skill
`planning`: он исследует репозиторий и задает уточняющие вопросы. После
создания файла завершите сессию GigaCode, чтобы GigaLphEx проверил и при
необходимости закоммитил план.

Для прежней одношаговой генерации без skill используйте:

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli --plan "добавить health check endpoint" --quick
```

При запуске без TTY, например в CI, quick-режим выбирается автоматически.

2. Откройте созданный файл в `docs/plans/`. Хороший план обычно содержит:

- краткие `Overview` и `Context` либо `Обзор` и `Контекст`;
- 2-6 независимых разделов `### Task N:` или `### Задача N:`;
- конкретные чекбоксы `- [ ] ...`;
- тесты и validation-команды внутри задач или в разделе `Validation`.

3. Если план слишком крупный или расплывчатый, отредактируйте его вручную.
   Это нормальный паттерн работы: план - не святыня, а контракт для агента.

4. Запустите выполнение:

В командах ниже замените имя plan-файла на тот файл, который был создан или
отредактирован у вас.

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli docs/plans/20260617-add-health-check-endpoint.md
```

По умолчанию раннер создаст или переключит git-ветку из имени плана. После
успешного полного прогона plan-файл будет перенесен в
`docs/plans/completed/`.

## Как понимать результат

Смотрите три места:

- `git log --oneline --decorate -10` - появились ли коммиты по задачам и ревью.
- `git status --short` - остались ли незакоммиченные изменения.
- `.gigalphex/progress/progress-<plan-name>.txt` - что делал GigaCode и на чем
  остановился.

Нормальный успешный прогон обычно выглядит так:

- каждая задача из плана отмечена `[x]`;
- по задачам есть один или несколько коммитов `feat: ...`;
- review-проход либо сделал `fix: address code review findings`, либо завершился
  сигналом `<<<GIGALPHEX:REVIEW_DONE>>>`;
- в progress log есть `<<<GIGALPHEX:ALL_TASKS_DONE>>>` или понятный путь к
  завершению;
- рабочее дерево чистое или содержит только ожидаемые локальные файлы.

## Полезные режимы

Посмотреть промпты без запуска GigaCode:

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli --dry-run docs/plans/20260617-add-health-check-endpoint.md
```

Выполнить только задачи, без review-фазы:

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli docs/plans/20260617-add-health-check-endpoint.md --tasks-only
```

Запустить только review текущей ветки относительно default branch:

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli --review
```

Запустить review текущей ветки относительно явно указанной ветки:

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli --review --base-ref develop
```

Review-агенты работают только на чтение и возвращают замечания. Исправления,
тесты и коммит `fix: address code review findings` выполняет только synthesis.
Review-агенты используют `review_model`, а synthesis — `task_model`, как и
основная реализация.
После успешного review по умолчанию выполняется finalize-проход. Отключить его
можно флагом `--no-finalize`.

Не переключать текущую ветку автоматически:

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli docs/plans/20260617-add-health-check-endpoint.md --no-branch
```

Запустить в отдельном git worktree, чтобы меньше трогать текущий checkout:

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli docs/plans/20260617-add-health-check-endpoint.md --worktree
```

Разрешить запуск с грязным рабочим деревом, если это осознанно:

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli docs/plans/20260617-add-health-check-endpoint.md --allow-dirty
```

## Паттерны хороших задач

Лучше всего подходят задачи, где можно быстро проверить результат:

- добавить маленькую фичу с тестами;
- исправить конкретный баг;
- улучшить обработку ошибки;
- обновить документацию вместе с поведением;
- сделать небольшой рефакторинг с сохранением тестов.

Плохо подходят для первого теста:

- задачи без понятного критерия готовности;
- большие архитектурные переделки на десятки файлов;
- задачи, где нельзя запускать тесты локально;
- изменения, требующие секретов, внешних доступов или ручных approvals;
- задачи, где нужно править файлы вне workspace GigaCode.

## Как писать plan-файл вручную

Минимальный формат:

```md
# Plan: Add health check endpoint

## Overview
Add a small endpoint that reports service health.

## Context
Inspect the web routing module and existing endpoint tests before editing.

### Task 1: Add endpoint
- [ ] Add the health check route.
- [ ] Add or update focused tests.
- [ ] Run the relevant test command.
- [ ] Commit the change.

### Task 2: Update documentation
- [ ] Document the endpoint.
- [ ] Run documentation or smoke validation if available.
- [ ] Commit the change.

## Validation
- run the service test suite
```

План можно полностью написать по-русски, включая заголовки:

```md
# План: Добавить health check endpoint

## Обзор
Добавить небольшой endpoint, сообщающий о состоянии сервиса.

## Контекст
Перед изменениями изучить роутинг и существующие тесты endpoint-ов.

### Задача 1: Добавить endpoint
- [ ] Добавить health check route.
- [ ] Добавить или обновить сфокусированные тесты.
- [ ] Запустить подходящую команду тестов.
- [ ] Сделать коммит.

## Проверка
- запустить тесты сервиса
```

Каждый `### Task N:` или `### Задача N:` должен быть независимо
коммитабельным. Если задача просит
сделать коммит, чекбокс должен становиться `[x]` только после успешного
`git commit`.

## Что фиксировать в обратной связи

Для полезного отчета достаточно коротко записать:

- какой проект и какая задача тестировались;
- команду запуска;
- ссылку или путь к plan-файлу;
- путь к progress log;
- что получилось хорошо;
- где агент застрял, ошибся или сделал лишнее;
- какие команды проверки запускались и чем завершились.

Особенно ценны кейсы, где план был хороший, но выполнение сломалось: такие
примеры помогают улучшать промпты, retry/timeout-настройки и контракт с
GigaCode.
