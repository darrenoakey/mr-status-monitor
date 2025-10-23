#!/usr/bin/env python3

from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex
from typing import List, Dict, Any

# ##################################################################
# merge request model
# qt model for displaying merge request data in qml listview
# handles data updates per repo while maintaining stable ordering
class MRModel(QAbstractListModel):
    RepoRole = Qt.UserRole + 1
    MRRole = Qt.UserRole + 2
    TitleRole = Qt.UserRole + 3
    StatusPillsRole = Qt.UserRole + 4
    MRUrlRole = Qt.UserRole + 5
    PipelineUrlRole = Qt.UserRole + 6
    BranchRole = Qt.UserRole + 7

    def __init__(self) -> None:
        super().__init__()
        self._data: List[Dict[str, Any]] = []

    # ##################################################################
    # row count
    # returns number of merge requests in the model
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._data)

    # ##################################################################
    # data accessor
    # retrieves specific field data for a merge request by role
    def data(self, index: QModelIndex, role: int) -> Any:
        if not index.isValid() or index.row() >= len(self._data):
            return None

        item = self._data[index.row()]

        if role == MRModel.RepoRole:
            return item['repo']
        elif role == MRModel.MRRole:
            return item['mr']
        elif role == MRModel.TitleRole:
            return item['title']
        elif role == MRModel.StatusPillsRole:
            return item['status_pills']
        elif role == MRModel.MRUrlRole:
            return item['mr_url']
        elif role == MRModel.PipelineUrlRole:
            return item['pipeline_url']
        elif role == MRModel.BranchRole:
            return item['branch']

        return None

    # ##################################################################
    # role names
    # maps qt roles to qml property names for data binding
    def roleNames(self) -> Dict[int, bytes]:
        return {
            MRModel.RepoRole: b"repo",
            MRModel.MRRole: b"mr",
            MRModel.TitleRole: b"title",
            MRModel.StatusPillsRole: b"statusPills",
            MRModel.MRUrlRole: b"mrUrl",
            MRModel.PipelineUrlRole: b"pipelineUrl",
            MRModel.BranchRole: b"branch"
        }

    # ##################################################################
    # add merge request
    # appends a new merge request to the model with unique key
    def add_mr(self, data: Dict[str, Any]) -> None:
        data['key'] = f"{data['repo']}-{data['mr']}"
        self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
        self._data.append(data)
        self.endInsertRows()

    # ##################################################################
    # update repository data
    # replaces all merge requests for a specific repo while maintaining order
    def update_repo_data(self, repo_name: str, new_items: List[Dict[str, Any]]) -> None:
        existing_items = {item['key']: item for item in self._data if item.get('key')}

        self.clear_repo(repo_name)

        for new_item in new_items:
            key = f"{repo_name}-{new_item['mr']}"
            new_item['key'] = key

            self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
            self._data.append(new_item)
            self.endInsertRows()

        self._sort_data()

    # ##################################################################
    # sort data
    # sorts merge requests by repo name then mr number for consistent display
    def _sort_data(self) -> None:
        if not self._data:
            return

        self.beginResetModel()
        self._data.sort(key=lambda x: (x.get('repo', ''), int(x.get('mr', '!0')[1:] or 0)))
        self.endResetModel()

    # ##################################################################
    # clear repository
    # removes all merge requests for a specific repository from model
    def clear_repo(self, repo_name: str) -> None:
        i = 0
        while i < len(self._data):
            if self._data[i]['repo'] == repo_name:
                self.beginRemoveRows(QModelIndex(), i, i)
                del self._data[i]
                self.endRemoveRows()
            else:
                i += 1

    # ##################################################################
    # clear all
    # removes all merge requests from the model
    def clear_all(self) -> None:
        self.beginResetModel()
        self._data.clear()
        self.endResetModel()
