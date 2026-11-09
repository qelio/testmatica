"use client";

// Комната на русском. Готовый VideoConference из LiveKit не переводится (надписи зашиты в код),
// поэтому раскладка повторяет его, а панель кнопок, чат и сообщения о связи — свои.

import {
  CarouselLayout,
  ChatEntry,
  ChatToggle,
  DisconnectButton,
  FocusLayout,
  FocusLayoutContainer,
  GridLayout,
  isTrackReference,
  LayoutContextProvider,
  MediaDeviceMenu,
  ParticipantTile,
  RoomAudioRenderer,
  StartMediaButton,
  TrackToggle,
  useChat,
  useConnectionState,
  useCreateLayoutContext,
  useLayoutContext,
  useLocalParticipantPermissions,
  usePersistentUserChoices,
  usePinnedTracks,
  useTracks,
  type TrackReferenceOrPlaceholder,
} from "@livekit/components-react";
import { ConnectionState, RoomEvent, Track } from "livekit-client";
import { useEffect, useRef, useState } from "react";

import { useScreenQuality } from "@/components/screen-quality";

type WidgetState = {
  showChat: boolean;
  unreadMessages: number;
  showSettings?: boolean;
};

function sameTrack(
  a?: TrackReferenceOrPlaceholder,
  b?: TrackReferenceOrPlaceholder,
): boolean {
  if (!a || !b) return false;
  return (
    a.participant.identity === b.participant.identity && a.source === b.source
  );
}

export function RuConference() {
  const [widget, setWidget] = useState<WidgetState>({
    showChat: false,
    unreadMessages: 0,
  });
  const layout = useCreateLayoutContext();
  const autoFocused = useRef<string | null>(null);
  useScreenQuality();

  const tracks = useTracks(
    [
      { source: Track.Source.Camera, withPlaceholder: true },
      { source: Track.Source.ScreenShare, withPlaceholder: false },
    ],
    { updateOnlyOn: [RoomEvent.ActiveSpeakersChanged], onlySubscribed: false },
  );
  const screens = tracks
    .filter(isTrackReference)
    .filter((t) => t.publication.source === Track.Source.ScreenShare);
  const focus = usePinnedTracks(layout)?.[0];
  const carousel = tracks.filter((t) => !sameTrack(t, focus));
  const screensKey = screens
    .map((t) => `${t.publication.trackSid}_${t.publication.isSubscribed}`)
    .join();

  // Кто-то показывает экран — он крупно; перестал — возвращаемся к сетке (как в VideoConference).
  useEffect(() => {
    const shown = screens.find((t) => t.publication.isSubscribed);
    if (shown && autoFocused.current === null) {
      layout.pin.dispatch?.({ msg: "set_pin", trackReference: shown });
      autoFocused.current = shown.publication.trackSid;
    } else if (
      autoFocused.current &&
      !screens.some((t) => t.publication.trackSid === autoFocused.current)
    ) {
      layout.pin.dispatch?.({ msg: "clear_pin" });
      autoFocused.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screensKey]);

  return (
    <div className="lk-video-conference">
      <LayoutContextProvider
        value={layout}
        onWidgetChange={(s) => setWidget(s as WidgetState)}
      >
        <div className="lk-video-conference-inner">
          {!focus ? (
            <div className="lk-grid-layout-wrapper">
              <GridLayout tracks={tracks}>
                <ParticipantTile />
              </GridLayout>
            </div>
          ) : (
            <div className="lk-focus-layout-wrapper">
              <FocusLayoutContainer>
                <CarouselLayout tracks={carousel}>
                  <ParticipantTile />
                </CarouselLayout>
                <FocusLayout trackRef={focus} />
              </FocusLayoutContainer>
            </div>
          )}
          <RuControlBar
            chatOpen={widget.showChat}
            unread={widget.unreadMessages}
          />
        </div>
        <RuChat open={widget.showChat} />
      </LayoutContextProvider>
      <RoomAudioRenderer />
      <ConnectionToast />
    </div>
  );
}

function useNarrow(query: string): boolean {
  const [match, setMatch] = useState(false);
  useEffect(() => {
    const m = window.matchMedia(query);
    const update = () => setMatch(m.matches);
    update();
    m.addEventListener("change", update);
    return () => m.removeEventListener("change", update);
  }, [query]);
  return match;
}

function RuControlBar({
  chatOpen,
  unread,
}: {
  chatOpen: boolean;
  unread: number;
}) {
  const permissions = useLocalParticipantPermissions();
  const narrow = useNarrow(`(max-width: ${chatOpen ? 1000 : 760}px)`);
  const [sharing, setSharing] = useState(false);
  const {
    saveAudioInputEnabled,
    saveVideoInputEnabled,
    saveAudioInputDeviceId,
    saveVideoInputDeviceId,
  } = usePersistentUserChoices();

  // Источники, которые разрешено публиковать (1 — камера, 2 — микрофон, 3 — экран).
  const can = (code: number) =>
    !!permissions?.canPublish &&
    (permissions.canPublishSources.length === 0 ||
      permissions.canPublishSources.includes(code));
  const screenSupported =
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getDisplayMedia;
  const text = (label: string) => (narrow ? null : label);

  return (
    <div className="lk-control-bar">
      {can(2) && (
        <div className="lk-button-group">
          <TrackToggle
            source={Track.Source.Microphone}
            showIcon
            onChange={(enabled, user) => user && saveAudioInputEnabled(enabled)}
            title="Микрофон"
          >
            {text("Микрофон")}
          </TrackToggle>
          <div className="lk-button-group-menu">
            <MediaDeviceMenu
              kind="audioinput"
              onActiveDeviceChange={(_k, id) =>
                saveAudioInputDeviceId(id ?? "default")
              }
              title="Выбрать микрофон"
            />
          </div>
        </div>
      )}
      {can(1) && (
        <div className="lk-button-group">
          <TrackToggle
            source={Track.Source.Camera}
            showIcon
            onChange={(enabled, user) => user && saveVideoInputEnabled(enabled)}
            title="Камера"
          >
            {text("Камера")}
          </TrackToggle>
          <div className="lk-button-group-menu">
            <MediaDeviceMenu
              kind="videoinput"
              onActiveDeviceChange={(_k, id) =>
                saveVideoInputDeviceId(id ?? "default")
              }
              title="Выбрать камеру"
            />
          </div>
        </div>
      )}
      {can(3) && screenSupported && (
        <TrackToggle
          source={Track.Source.ScreenShare}
          captureOptions={{ audio: true, selfBrowserSurface: "include", contentHint: "text" }}
          showIcon
          onChange={setSharing}
          title={sharing ? "Остановить показ экрана" : "Показать экран"}
        >
          {text(sharing ? "Остановить показ" : "Показать экран")}
        </TrackToggle>
      )}
      {!!permissions?.canPublishData && (
        <ChatToggle title="Чат">
          <ChatIcon />
          {text("Чат")}
          {unread > 0 && !chatOpen && (
            <span className="ml-1 rounded-full bg-brand px-1.5 text-xs text-on-brand">
              {unread}
            </span>
          )}
        </ChatToggle>
      )}
      <DisconnectButton title="Выйти из занятия">
        <LeaveIcon />
        {text("Выйти")}
      </DisconnectButton>
      <StartMediaButton label="Включить звук и видео" />
    </div>
  );
}

function RuChat({ open }: { open: boolean }) {
  const { chatMessages, send, isSending } = useChat();
  const layout = useLayoutContext();
  const list = useRef<HTMLUListElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const lastRead = useRef<number | undefined>(undefined);

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight });
  }, [chatMessages]);

  // Непрочитанные — счётчик на кнопке «Чат», пока чат закрыт.
  useEffect(() => {
    if (!chatMessages.length) return;
    const last = chatMessages[chatMessages.length - 1].timestamp;
    if (open) {
      lastRead.current = last;
      if (layout.widget.state?.unreadMessages)
        layout.widget.dispatch?.({ msg: "unread_msg", count: 0 });
      return;
    }
    const unread = chatMessages.filter(
      (m) => !lastRead.current || m.timestamp > lastRead.current,
    ).length;
    if (unread !== layout.widget.state?.unreadMessages)
      layout.widget.dispatch?.({ msg: "unread_msg", count: unread });
  }, [chatMessages, open, layout.widget]);

  return (
    <div className="lk-chat" style={{ display: open ? "grid" : "none" }}>
      <div className="lk-chat-header">
        Чат занятия
        <ChatToggle className="lk-close-button" title="Закрыть чат">
          ✕
        </ChatToggle>
      </div>
      <ul className="lk-list lk-chat-messages" ref={list}>
        {chatMessages.length === 0 && (
          <li className="p-3 text-sm opacity-70">
            Сообщений пока нет. Чат виден всем участникам, пока идёт занятие.
          </li>
        )}
        {chatMessages.map((msg, i, all) => {
          const hideName = i >= 1 && all[i - 1].from === msg.from;
          const hideTimestamp =
            i >= 1 && msg.timestamp - all[i - 1].timestamp < 60_000;
          return (
            <ChatEntry
              key={msg.id ?? i}
              entry={msg}
              hideName={hideName}
              hideTimestamp={hideName ? hideTimestamp : false}
            />
          );
        })}
      </ul>
      <form
        className="lk-chat-form"
        onSubmit={async (e) => {
          e.preventDefault();
          const value = input.current?.value.trim();
          if (!value) return;
          await send(value);
          input.current!.value = "";
          input.current!.focus();
        }}
      >
        <input
          className="lk-form-control lk-chat-form-input"
          disabled={isSending}
          ref={input}
          type="text"
          placeholder="Сообщение…"
          aria-label="Сообщение в чат"
        />
        <button
          type="submit"
          className="lk-button lk-chat-form-button"
          disabled={isSending}
        >
          Отправить
        </button>
      </form>
    </div>
  );
}

function ConnectionToast() {
  const state = useConnectionState();
  const text =
    state === ConnectionState.Reconnecting ||
    state === ConnectionState.SignalReconnecting
      ? "Связь прервалась — переподключаемся…"
      : state === ConnectionState.Connecting
        ? "Подключаемся…"
        : null;
  if (!text) return null;
  return (
    <div className="lk-toast lk-toast-connection-state" role="status">
      {text}
    </div>
  );
}

function ChatIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden
    >
      <path d="M2 3.5h12v7H6l-3 2.5v-2.5H2z" strokeLinejoin="round" />
    </svg>
  );
}

function LeaveIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden
    >
      <path
        d="M6 2.5H3v11h3M10 5l3 3-3 3M13 8H6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
