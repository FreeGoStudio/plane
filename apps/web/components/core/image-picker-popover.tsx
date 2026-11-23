/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import React, { useState, useRef, useCallback, useMemo } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { useDropzone } from "react-dropzone";
import type { Control, FieldPath, FieldValues } from "react-hook-form";
import { Controller } from "react-hook-form";
import useSWR from "swr";
// plane imports
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { Popover, PopoverBody, PopoverContent, PopoverTrigger } from "@makeplane/propel/components/popover";
import { Tab, Tabs, TabsList, TabsPanel } from "@makeplane/propel/components/tabs";
import { ACCEPTED_COVER_IMAGE_MIME_TYPES_FOR_REACT_DROPZONE, MAX_FILE_SIZE } from "@plane/constants";
import { Button } from "@makeplane/propel/components/button";
import { Button as ButtonElement } from "@makeplane/propel/elements/button";
import { setToast } from "@plane/blocks/toast";
import { EFileAssetType } from "@plane/types";
import { Loader } from "@plane/blocks/skeleton";
// helpers
import { STATIC_COVER_IMAGES, getCoverImageDisplayURL } from "@/helpers/cover-image.helper";
// hooks
import { useInstance } from "@/hooks/store/use-instance";
// services
import { FileService } from "@/services/file.service";

type TTabOption = {
  key: string;
  title: string;
  isEnabled: boolean;
};

// Generic over the form's values because react-hook-form's Control is invariant: its
// `_options.validate` narrows `name` to a keyof union, so `Control<any>` no longer
// accepts a typed form's control. Inferring from `control` keeps call sites unchanged.
type Props<TFieldValues extends FieldValues = FieldValues> = {
  label: string | React.ReactNode;
  value: string | null;
  control: Control<TFieldValues>;
  onChange: (data: string) => void;
  disabled?: boolean;
  tabIndex?: number;
  isProfileCover?: boolean;
  projectId?: string | null;
};

// services
const fileService = new FileService();

function ImagePickerPopoverComponent<TFieldValues extends FieldValues = FieldValues>(props: Props<TFieldValues>) {
  const { t } = useTranslation();

  const {
    label,
    value: localValue0,
    control,
    onChange,
    disabled = false,
    tabIndex,
    isProfileCover = false,
    projectId,
  } = props;
  // states
  const [localImage1, setImage] = useState<File | null>(null);
  const [isImageUploading, setIsImageUploading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [searchParams, setSearchParams] = useState("");
  const [formData, setFormData] = useState({
    search: "",
  });
  // router params
  const { workspaceSlug } = useParams();
  // store hooks
  const { config } = useInstance();
  // derived values
  const hasUnsplashConfigured = config?.has_unsplash_configured || false;
  const tabOptions: TTabOption[] = useMemo(
    () => [
      {
        key: "unsplash",
        title: "Unsplash",
        isEnabled: hasUnsplashConfigured,
      },
      {
        key: "images",
        title: t("web_ui.images"),
        isEnabled: true,
      },
      {
        key: "upload",
        title: t("web_ui.upload"),
        isEnabled: true,
      },
    ],
    [t, hasUnsplashConfigured]
  );

  const enabledTabs = useMemo(() => tabOptions.filter((tab) => tab.isEnabled), [tabOptions]);

  const { data: unsplashImages, error: unsplashError } = useSWR(
    `UNSPLASH_IMAGES_${searchParams}`,
    () => fileService.getUnsplashImages(searchParams),
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
    }
  );

  const imagePickerRef = useRef<HTMLDivElement>(null);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    setImage(acceptedFiles[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    accept: ACCEPTED_COVER_IMAGE_MIME_TYPES_FOR_REACT_DROPZONE,
    maxSize: MAX_FILE_SIZE,
  });

  const handleStaticImageSelect = (imageUrl: string) => {
    onChange(imageUrl);
    setIsOpen(false);
  };

  const handleSubmit = async () => {
    if (!localImage1) return;
    setIsImageUploading(true);

    const uploadCallback = (url: string) => {
      onChange(url);
      setIsImageUploading(false);
      setImage(null);
      setIsOpen(false);
    };

    if (isProfileCover) {
      await fileService
        .uploadUserAsset(
          {
            entity_identifier: "",
            entity_type: EFileAssetType.USER_COVER,
          },
          localImage1
        )
        .then((res) => uploadCallback(res.asset_url))
        .catch((error) => {
          console.error("Error uploading user cover image:", error);
          setIsImageUploading(false);
          setToast({
            message: error?.error ?? "The image could not be uploaded",
            type: "error",
            title: t("web_ui.image_not_uploaded"),
          });
        });
    } else {
      if (!workspaceSlug) return;
      await fileService
        .uploadWorkspaceAsset(
          workspaceSlug.toString(),
          {
            entity_identifier: projectId?.toString() ?? "",
            entity_type: EFileAssetType.PROJECT_COVER,
          },
          localImage1
        )
        .then((res) => uploadCallback(res.asset_url))
        .catch((error) => {
          console.error("Error uploading project cover image:", error);
          setIsImageUploading(false);
          setToast({
            message: error?.error ?? "The image could not be uploaded",
            type: "error",
            title: t("web_ui.image_not_uploaded"),
          });
        });
    }
  };

  return (
    // The popover owns the portal, positioning, outside press and Escape, so the outside-click
    // detector and the dropdown key handler go (Ruling 36).
    <div className="relative z-19">
      <Popover open={isOpen} onOpenChange={setIsOpen}>
        <PopoverTrigger
          disabled={disabled}
          render={
            <ButtonElement
              variant="secondary"
              size="xs"
              stretch="auto"
              disabled={disabled}
              tabIndex={tabIndex}
              // The trigger sits inside clickable cover-image chrome; the press must not reach it.
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
              }}
            />
          }
        >
          {label}
        </PopoverTrigger>
        <PopoverContent variant="rich" side="bottom" align="end" sideOffset={8} data-prevent-outside-click>
          <PopoverBody tabIndex={0}>
            <div
              ref={imagePickerRef}
              className="flex h-96 w-80 max-w-full flex-col overflow-auto md:h-[36rem] md:w-[36rem]"
            >
              <Tabs variant="contained" stretch="full" layout="fill" defaultValue={enabledTabs[0]?.key || "images"}>
                <TabsList>
                  {enabledTabs.map((tab) => (
                    <Tab key={tab.key} value={tab.key} label={tab.title} />
                  ))}
                </TabsList>
                <div className="vertical-scrollbar mt-4 scrollbar-sm flex min-h-0 w-full flex-1 flex-col overflow-auto">
                  <TabsPanel value="unsplash">
                    <div className="flex h-full min-h-0 w-full flex-col">
                      {(unsplashImages || !unsplashError) && (
                        <>
                          <div className="mb-4 flex flex-shrink-0 items-center gap-x-3">
                            <div className="min-w-0 flex-1">
                              <Controller
                                control={control}
                                name={"search" as FieldPath<TFieldValues>}
                                render={({ field: { value, ref } }) => (
                                  <InputGroup size="lg">
                                    <Input
                                      size="lg"
                                      id="search"
                                      name="search"
                                      type="text"
                                      onKeyDown={(e) => {
                                        if (e.key === "Enter") {
                                          e.preventDefault();
                                          setSearchParams(formData.search);
                                        }
                                      }}
                                      value={value}
                                      onChange={(e) => setFormData({ ...formData, search: e.target.value })}
                                      ref={ref}
                                      placeholder={t("web_ui.search_for_images")}
                                    />
                                  </InputGroup>
                                )}
                              />
                            </div>
                            <Button
                              variant="primary"
                              size="lg"
                              stretch="auto"
                              label={t("search")}
                              onClick={() => setSearchParams(formData.search)}
                            />
                          </div>
                          {unsplashImages ? (
                            unsplashImages.length > 0 ? (
                              <div className="grid grid-cols-4 gap-4">
                                {unsplashImages.map((image) => (
                                  <button
                                    type="button"
                                    key={image.id}
                                    className="relative col-span-2 aspect-video md:col-span-1"
                                    aria-label={
                                      image.alt_description
                                        ? `Select image: ${image.alt_description}`
                                        : t("web_ui.select_image")
                                    }
                                    onClick={() => {
                                      setIsOpen(false);
                                      onChange(image.urls.regular);
                                    }}
                                  >
                                    <img
                                      src={image.urls.small}
                                      alt={image.alt_description}
                                      className="absolute top-0 left-0 h-full w-full cursor-pointer rounded-sm object-cover transition-opacity hover:opacity-80"
                                    />
                                  </button>
                                ))}
                              </div>
                            ) : (
                              <div className="flex min-h-0 flex-1 items-center justify-center">
                                <p className="text-center text-caption-md-regular text-tertiary">No images found.</p>
                              </div>
                            )
                          ) : (
                            <Loader className="grid grid-cols-4 gap-4">
                              <Loader.Item height="80px" width="100%" />
                              <Loader.Item height="80px" width="100%" />
                              <Loader.Item height="80px" width="100%" />
                              <Loader.Item height="80px" width="100%" />
                              <Loader.Item height="80px" width="100%" />
                              <Loader.Item height="80px" width="100%" />
                              <Loader.Item height="80px" width="100%" />
                              <Loader.Item height="80px" width="100%" />
                            </Loader>
                          )}
                        </>
                      )}
                    </div>
                  </TabsPanel>
                  <TabsPanel value="images">
                    <div className="grid grid-cols-4 gap-4">
                      {Object.values(STATIC_COVER_IMAGES).map((imageUrl, index) => (
                        <button
                          type="button"
                          key={imageUrl}
                          className="relative col-span-2 aspect-video md:col-span-1"
                          aria-label={t("web_ui.dynamic_select_cover_image_value0", { value0: index + 1 })}
                          onClick={() => handleStaticImageSelect(imageUrl)}
                        >
                          <img
                            src={imageUrl}
                            alt={t("web_ui.dynamic_cover_image_value0", { value0: index + 1 })}
                            className="absolute top-0 left-0 h-full w-full cursor-pointer rounded-sm object-cover transition-opacity hover:opacity-80"
                          />
                        </button>
                      ))}
                    </div>
                  </TabsPanel>
                  <TabsPanel value="upload">
                    <div className="flex h-full w-full flex-col gap-y-2">
                      <div className="flex w-full flex-1 items-center gap-3">
                        <div
                          {...getRootProps()}
                          className={`relative grid h-full w-full cursor-pointer place-items-center rounded-lg p-12 text-center focus:ring-2 focus:ring-accent-strong focus:ring-offset-2 focus:outline-none ${
                            (localImage1 === null && isDragActive) || !localValue0
                              ? "border-2 border-dashed border-subtle hover:bg-surface-2"
                              : ""
                          }`}
                        >
                          <div className="absolute top-0 right-1 z-40">
                            <Button type="button" variant="tertiary" size="xs" stretch="auto" label="Edit" />
                          </div>
                          {localImage1 !== null || (localValue0 && localValue0 !== "") ? (
                            <>
                              <img
                                src={
                                  localImage1
                                    ? URL.createObjectURL(localImage1)
                                    : getCoverImageDisplayURL(localValue0, "")
                                }
                                alt={t("web_ui.image")}
                                className="h-full w-full rounded-lg object-cover"
                              />
                            </>
                          ) : (
                            <div>
                              <span className="mt-2 block text-body-xs-medium text-secondary">
                                {isDragActive ? t("web_ui.drop_image_here_to_upload") : "Drag & drop image here"}
                              </span>
                            </div>
                          )}

                          <input {...getInputProps()} />
                        </div>
                      </div>
                      {fileRejections.length > 0 && (
                        <p className="text-body-xs-regular text-danger-primary">
                          {fileRejections[0].errors[0].code === "file-too-large"
                            ? "The image size cannot exceed 5 MB."
                            : t("web_ui.please_upload_a_file_in_a_valid_format")}
                        </p>
                      )}

                      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-1">
                        <p className="min-w-0 truncate text-body-xs-regular text-secondary">
                          File formats supported- .jpeg, .jpg, .png, .webp
                        </p>
                        <div className="flex flex-shrink-0 items-center gap-2">
                          <Button
                            variant="secondary"
                            size="md"
                            stretch="auto"
                            label={t("cancel")}
                            onClick={() => {
                              setIsOpen(false);
                              setImage(null);
                            }}
                          />
                          <Button
                            variant="primary"
                            size="md"
                            stretch="auto"
                            label={
                              isImageUploading
                                ? t("project.members_import.progress.uploading")
                                : t("workspace_settings.settings.applications.upload_and_save")
                            }
                            onClick={handleSubmit}
                            disabled={!localImage1}
                            loading={isImageUploading}
                          />
                        </div>
                      </div>
                    </div>
                  </TabsPanel>
                </div>
              </Tabs>
            </div>
          </PopoverBody>
        </PopoverContent>
      </Popover>
    </div>
  );
}

// observer() erases the generic signature, so restore it with a cast.
export const ImagePickerPopover = observer(ImagePickerPopoverComponent) as typeof ImagePickerPopoverComponent;
